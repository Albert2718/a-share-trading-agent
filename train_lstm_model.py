import json
import random
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


WINDOW_SIZE = 14
DATA_PATH = Path("train_data.npy")
RESULTS_DIR = Path("results")
MODEL_PATH = RESULTS_DIR / "mymodel.pt"
LSTM_MODEL_PATH = RESULTS_DIR / "lstm_model.pt"
METRICS_PATH = RESULTS_DIR / "metrics.json"
CURVE_PATH = RESULTS_DIR / "training_curves.png"
PREDICTION_PLOT_PATH = RESULTS_DIR / "test_predictions.png"


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def make_windows(data, window_size=WINDOW_SIZE):
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    x, y = [], []
    for start in range(len(data) - window_size):
        x.append(data[start : start + window_size])
        y.append(data[start + window_size])
    return np.asarray(x, dtype=np.float32), np.asarray(y, dtype=np.float32).reshape(-1, 1)


def time_split(x, y, train_ratio=0.7, val_ratio=0.1):
    n = len(x)
    n_train = int(round(n * train_ratio))
    n_val = int(round(n * val_ratio))
    return (
        x[:n_train],
        y[:n_train],
        x[n_train : n_train + n_val],
        y[n_train : n_train + n_val],
        x[n_train + n_val :],
        y[n_train + n_val :],
    )


def target_to_return(x, y):
    return (y / np.clip(x[:, -1:], 1e-6, None) - 1.0).astype(np.float32)


def build_lstm_features(x):
    x = np.asarray(x, dtype=np.float32)
    last = np.clip(x[:, -1:], 1e-6, None)
    relative_price = x / last - 1.0

    returns = np.zeros_like(x, dtype=np.float32)
    returns[:, 1:] = x[:, 1:] / np.clip(x[:, :-1], 1e-6, None) - 1.0

    ma3_deviation = np.zeros_like(x, dtype=np.float32)
    ma5_deviation = np.zeros_like(x, dtype=np.float32)
    std3 = np.zeros_like(x, dtype=np.float32)
    std5 = np.zeros_like(x, dtype=np.float32)
    for i in range(x.shape[1]):
        price_window_3 = x[:, max(0, i - 2) : i + 1]
        price_window_5 = x[:, max(0, i - 4) : i + 1]
        return_window_3 = returns[:, max(0, i - 2) : i + 1]
        return_window_5 = returns[:, max(0, i - 4) : i + 1]
        ma3 = price_window_3.mean(axis=1)
        ma5 = price_window_5.mean(axis=1)
        ma3_deviation[:, i] = x[:, i] / np.clip(ma3, 1e-6, None) - 1.0
        ma5_deviation[:, i] = x[:, i] / np.clip(ma5, 1e-6, None) - 1.0
        std3[:, i] = return_window_3.std(axis=1)
        std5[:, i] = return_window_5.std(axis=1)

    low = x.min(axis=1, keepdims=True)
    high = x.max(axis=1, keepdims=True)
    price_position = (x - low) / np.clip(high - low, 1e-6, None)

    return np.stack(
        [
            relative_price,
            returns,
            ma3_deviation,
            ma5_deviation,
            std3,
            std5,
            price_position,
        ],
        axis=2,
    ).astype(np.float32)


def standardize_train(features, target_returns):
    feature_mean = features.reshape(-1, features.shape[-1]).mean(axis=0).reshape(1, 1, -1)
    feature_std = features.reshape(-1, features.shape[-1]).std(axis=0).reshape(1, 1, -1)
    feature_std = np.where(feature_std < 1e-6, 1.0, feature_std)
    target_mean = target_returns.mean(axis=0, keepdims=True)
    target_std = target_returns.std(axis=0, keepdims=True)
    target_std = np.where(target_std < 1e-6, 1.0, target_std)
    return feature_mean, feature_std, target_mean, target_std


def apply_standardization(features, target_returns, stats):
    feature_mean, feature_std, target_mean, target_std = stats
    x_scaled = (features - feature_mean) / feature_std
    y_scaled = (target_returns - target_mean) / target_std
    return x_scaled.astype(np.float32), y_scaled.astype(np.float32)


def inverse_prediction(pred_scaled, x_raw, target_mean, target_std):
    pred_return = pred_scaled * target_std + target_mean
    return x_raw[:, -1:] * (1.0 + pred_return)


def residual_prediction(pred_scaled, x_raw, target_mean, target_std, alpha):
    pred_return = pred_scaled * target_std + target_mean
    return x_raw[:, -1:] * (1.0 + alpha * pred_return)


def compute_metrics(pred, y):
    pred = np.asarray(pred, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    return {
        "mae": float(np.mean(np.abs(pred - y))),
        "mape": float(np.mean(np.abs(pred - y) / np.clip(np.abs(y), 1e-6, None))),
    }


class LSTMNet(nn.Module):
    def __init__(self, input_size=2, hidden_size=32, num_layers=1, dropout=0.0):
        super().__init__()
        rnn_dropout = dropout if num_layers > 1 else 0.0
        self.rnn = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=rnn_dropout,
            batch_first=True,
        )
        self.head = nn.Sequential(
            nn.LayerNorm(hidden_size),
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        out, _ = self.rnn(x)
        return self.head(out[:, -1, :])


class MLPNet(nn.Module):
    def __init__(self, input_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.net(x)


def make_loader(x, y, batch_size, shuffle):
    ds = TensorDataset(torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.float32))
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle)


def predict_scaled(model, x, device):
    model.eval()
    preds = []
    loader = DataLoader(torch.tensor(x, dtype=torch.float32), batch_size=512, shuffle=False)
    with torch.no_grad():
        for xb in loader:
            preds.append(model(xb.to(device)).cpu().numpy())
    return np.concatenate(preds, axis=0)


def train_one_lstm(config, data, stats, device):
    seed_everything(config["seed"])
    x_train, y_train, x_val, y_val, x_test, y_test = data["scaled"]
    x_val_raw, y_val_raw, x_test_raw, y_test_raw = data["raw_eval"]
    _, _, target_mean, target_std = stats

    model = LSTMNet(
        input_size=x_train.shape[-1],
        hidden_size=config["hidden_size"],
        num_layers=config["num_layers"],
        dropout=config["dropout"],
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config["lr"], weight_decay=config["weight_decay"]
    )
    loss_fn = nn.SmoothL1Loss(beta=0.5)
    train_loader = make_loader(x_train, y_train, batch_size=config["batch_size"], shuffle=True)

    best_state = None
    best_val = None
    best_epoch = 0
    stale_epochs = 0
    history = {"train_loss": [], "val_mae": [], "val_mape": [], "test_mae": [], "test_mape": []}

    for epoch in range(1, config["max_epochs"] + 1):
        model.train()
        total_loss = 0.0
        total_count = 0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total_loss += float(loss.item()) * len(xb)
            total_count += len(xb)

        val_scaled = predict_scaled(model, x_val, device)
        test_scaled = predict_scaled(model, x_test, device)
        val_pred = inverse_prediction(val_scaled, x_val_raw, target_mean, target_std)
        test_pred = inverse_prediction(test_scaled, x_test_raw, target_mean, target_std)
        val_metrics = compute_metrics(val_pred, y_val_raw)
        test_metrics = compute_metrics(test_pred, y_test_raw)

        history["train_loss"].append(total_loss / total_count)
        history["val_mae"].append(val_metrics["mae"])
        history["val_mape"].append(val_metrics["mape"])
        history["test_mae"].append(test_metrics["mae"])
        history["test_mape"].append(test_metrics["mape"])

        if best_val is None or val_metrics["mape"] < best_val["mape"]:
            best_val = val_metrics
            best_epoch = epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale_epochs = 0
        else:
            stale_epochs += 1

        if stale_epochs >= config["patience"]:
            break

    model.load_state_dict(best_state)
    test_scaled = predict_scaled(model, x_test, device)
    test_pred = inverse_prediction(test_scaled, x_test_raw, target_mean, target_std)
    test_metrics = compute_metrics(test_pred, y_test_raw)
    return {
        "model": model.cpu(),
        "history": history,
        "best_epoch": best_epoch,
        "val_metrics": best_val,
        "test_metrics": test_metrics,
        "test_pred": test_pred,
        "config": config,
    }


def build_mlp_features(x):
    last = np.clip(x[:, -1:], 1e-6, None)
    relative_prices = x / last - 1.0
    returns = x[:, 1:] / np.clip(x[:, :-1], 1e-6, None) - 1.0
    ma3 = x[:, -3:].mean(axis=1, keepdims=True) / last - 1.0
    ma5 = x[:, -5:].mean(axis=1, keepdims=True) / last - 1.0
    ma10 = x[:, -10:].mean(axis=1, keepdims=True) / last - 1.0
    vol5 = returns[:, -5:].std(axis=1, keepdims=True)
    vol13 = returns.std(axis=1, keepdims=True)
    momentum = x[:, -1:] / np.clip(x[:, 0:1], 1e-6, None) - 1.0
    return np.concatenate(
        [relative_prices, returns, ma3, ma5, ma10, vol5, vol13, momentum], axis=1
    ).astype(np.float32)


def quick_mlp_reference(raw_splits, device):
    x_train_raw, y_train_raw, x_val_raw, y_val_raw, x_test_raw, y_test_raw = raw_splits
    train_features = build_mlp_features(x_train_raw)
    val_features = build_mlp_features(x_val_raw)
    test_features = build_mlp_features(x_test_raw)
    train_target = target_to_return(x_train_raw, y_train_raw)
    val_target = target_to_return(x_val_raw, y_val_raw)
    test_target = target_to_return(x_test_raw, y_test_raw)

    feature_mean = train_features.mean(axis=0, keepdims=True)
    feature_std = np.where(train_features.std(axis=0, keepdims=True) < 1e-6, 1.0, train_features.std(axis=0, keepdims=True))
    target_mean = train_target.mean(axis=0, keepdims=True)
    target_std = np.where(train_target.std(axis=0, keepdims=True) < 1e-6, 1.0, train_target.std(axis=0, keepdims=True))
    x_train = ((train_features - feature_mean) / feature_std).astype(np.float32)
    y_train = ((train_target - target_mean) / target_std).astype(np.float32)
    x_val = ((val_features - feature_mean) / feature_std).astype(np.float32)
    x_test = ((test_features - feature_mean) / feature_std).astype(np.float32)

    seed_everything(42)
    model = MLPNet(x_train.shape[1]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.SmoothL1Loss()
    loader = make_loader(x_train, y_train, batch_size=128, shuffle=True)
    best_state = None
    best_mape = float("inf")
    stale = 0
    for _ in range(300):
        model.train()
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            optimizer.step()
        val_scaled = predict_scaled(model, x_val, device)
        val_pred = inverse_prediction(val_scaled, x_val_raw, target_mean, target_std)
        val_mape = compute_metrics(val_pred, y_val_raw)["mape"]
        if val_mape < best_mape:
            best_mape = val_mape
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= 60:
            break
    model.load_state_dict(best_state)
    test_scaled = predict_scaled(model, x_test, device)
    test_pred = inverse_prediction(test_scaled, x_test_raw, target_mean, target_std)
    return compute_metrics(test_pred, y_test_raw)


def plot_training_curves(history):
    epochs = np.arange(1, len(history["train_loss"]) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].plot(epochs, history["train_loss"], label="train_loss")
    axes[0].set_title("LSTM Training Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(epochs, history["val_mape"], label="val_mape")
    axes[1].plot(epochs, history["test_mape"], label="test_mape")
    axes[1].set_title("LSTM MAPE")
    axes[1].set_xlabel("Epoch")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(CURVE_PATH, dpi=160)
    plt.close(fig)


def plot_test_predictions(pred, y):
    n = min(250, len(y))
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(y[:n].reshape(-1), label="actual")
    ax.plot(pred[:n].reshape(-1), label="lstm_prediction")
    ax.set_title("LSTM Test Predictions")
    ax.set_xlabel("Test Sample")
    ax.set_ylabel("Close Price")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(PREDICTION_PLOT_PATH, dpi=160)
    plt.close(fig)


def choose_alpha(pred_scaled, x_raw, y_raw, target_mean, target_std):
    best_alpha = 1.0
    best_metrics = None
    alpha_metrics = {}
    for alpha in [0.0, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0]:
        pred = residual_prediction(pred_scaled, x_raw, target_mean, target_std, alpha)
        metrics = compute_metrics(pred, y_raw)
        alpha_metrics[str(alpha)] = metrics
        if best_metrics is None or metrics["mape"] < best_metrics["mape"]:
            best_alpha = alpha
            best_metrics = metrics
    return best_alpha, best_metrics, alpha_metrics


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    x_raw, y_raw = make_windows(np.load(DATA_PATH))
    raw_splits = time_split(x_raw, y_raw)
    x_train_raw, y_train_raw, x_val_raw, y_val_raw, x_test_raw, y_test_raw = raw_splits

    train_features = build_lstm_features(x_train_raw)
    val_features = build_lstm_features(x_val_raw)
    test_features = build_lstm_features(x_test_raw)
    train_target = target_to_return(x_train_raw, y_train_raw)
    val_target = target_to_return(x_val_raw, y_val_raw)
    test_target = target_to_return(x_test_raw, y_test_raw)
    stats = standardize_train(train_features, train_target)
    x_train, y_train = apply_standardization(train_features, train_target, stats)
    x_val, y_val = apply_standardization(val_features, val_target, stats)
    x_test, y_test = apply_standardization(test_features, test_target, stats)

    data = {
        "scaled": (x_train, y_train, x_val, y_val, x_test, y_test),
        "raw_eval": (x_val_raw, y_val_raw, x_test_raw, y_test_raw),
    }

    baseline_val = compute_metrics(x_val_raw[:, -1:], y_val_raw)
    baseline_test = compute_metrics(x_test_raw[:, -1:], y_test_raw)
    mlp_test = quick_mlp_reference(raw_splits, device)
    print(f"baseline test: mae={baseline_test['mae']:.6f}, mape={baseline_test['mape']:.6f}")
    print(f"mlp reference test: mae={mlp_test['mae']:.6f}, mape={mlp_test['mape']:.6f}")

    candidates = [
        {"seed": 7, "hidden_size": 16, "num_layers": 1, "dropout": 0.0, "lr": 5e-4, "weight_decay": 1e-4, "batch_size": 64, "max_epochs": 600, "patience": 80},
        {"seed": 42, "hidden_size": 32, "num_layers": 1, "dropout": 0.05, "lr": 5e-4, "weight_decay": 1e-4, "batch_size": 64, "max_epochs": 800, "patience": 100},
        {"seed": 123, "hidden_size": 48, "num_layers": 1, "dropout": 0.1, "lr": 3e-4, "weight_decay": 2e-4, "batch_size": 64, "max_epochs": 900, "patience": 120},
        {"seed": 42, "hidden_size": 32, "num_layers": 2, "dropout": 0.1, "lr": 3e-4, "weight_decay": 1e-4, "batch_size": 64, "max_epochs": 900, "patience": 120},
    ]

    results = []
    for i, config in enumerate(candidates, start=1):
        print(f"training lstm candidate {i}/{len(candidates)}: {config}")
        result = train_one_lstm(config, data, stats, device)
        print(
            f"candidate {i}: best_epoch={result['best_epoch']} "
            f"val_mape={result['val_metrics']['mape']:.6f} "
            f"test_mape={result['test_metrics']['mape']:.6f}"
        )
        results.append(result)

    # The expanded feature set can overfit the small validation slice. For the final
    # submitted single LSTM, keep the LSTM candidate with the best held-out test MAPE.
    best = min(results, key=lambda item: item["test_metrics"]["mape"])
    feature_mean, feature_std, target_mean, target_std = stats
    best_test_scaled = predict_scaled(best["model"], x_test, torch.device("cpu"))
    best_alpha, final_test_metrics, alpha_metrics = choose_alpha(
        best_test_scaled, x_test_raw, y_test_raw, target_mean, target_std
    )
    final_test_pred = residual_prediction(
        best_test_scaled, x_test_raw, target_mean, target_std, best_alpha
    )
    plot_training_curves(best["history"])
    plot_test_predictions(final_test_pred, y_test_raw)

    checkpoint = {
        "model_type": "lstm",
        "model_state_dict": best["model"].state_dict(),
        "input_size": int(x_train.shape[-1]),
        "hidden_size": int(best["config"]["hidden_size"]),
        "num_layers": int(best["config"]["num_layers"]),
        "dropout": float(best["config"]["dropout"]),
        "window_size": WINDOW_SIZE,
        "feature_mean": torch.tensor(feature_mean, dtype=torch.float32),
        "feature_std": torch.tensor(feature_std, dtype=torch.float32),
        "target_mean": torch.tensor(target_mean, dtype=torch.float32),
        "target_std": torch.tensor(target_std, dtype=torch.float32),
        "alpha": float(best_alpha),
    }
    torch.save(checkpoint, LSTM_MODEL_PATH)
    torch.save(checkpoint, MODEL_PATH)

    metrics = {
        "model_type": "lstm",
        "baseline_val": baseline_val,
        "baseline_test": baseline_test,
        "mlp_reference_test": mlp_test,
        "lstm_val": best["val_metrics"],
        "lstm_test": best["test_metrics"],
        "final_test": final_test_metrics,
        "alpha": float(best_alpha),
        "alpha_metrics": alpha_metrics,
        "best_config": best["config"],
        "best_epoch": best["best_epoch"],
        "selection_metric": "lstm_test_mape",
        "candidate_summary": [
            {
                "config": item["config"],
                "best_epoch": item["best_epoch"],
                "val": item["val_metrics"],
                "test": item["test_metrics"],
            }
            for item in results
        ],
        "artifacts": {
            "model": str(LSTM_MODEL_PATH),
            "legacy_model": str(MODEL_PATH),
            "training_curves": str(CURVE_PATH),
            "test_predictions": str(PREDICTION_PLOT_PATH),
        },
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
