import json
import random
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


WINDOW_SIZE = 14
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "experiments" / "train_data.npy"
RESULTS_DIR = PROJECT_ROOT / "artifacts" / "models"
MODEL_PATH = RESULTS_DIR / "mymodel.pt"
METRICS_PATH = RESULTS_DIR / "metrics.json"
CURVE_PATH = RESULTS_DIR / "training_curves.png"
PREDICTION_PLOT_PATH = RESULTS_DIR / "test_predictions.png"


def seed_everything(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def make_windows(data, window_size=WINDOW_SIZE):
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    x, y = [], []
    for start in range(0, len(data) - window_size):
        x.append(data[start : start + window_size])
        y.append(data[start + window_size])
    return np.asarray(x, dtype=np.float32), np.asarray(y, dtype=np.float32).reshape(-1, 1)


def time_split(x, y, train_ratio=0.7, val_ratio=0.1):
    n = len(x)
    n_train = int(round(n * train_ratio))
    n_val = int(round(n * val_ratio))
    x_train, y_train = x[:n_train], y[:n_train]
    x_val, y_val = x[n_train : n_train + n_val], y[n_train : n_train + n_val]
    x_test, y_test = x[n_train + n_val :], y[n_train + n_val :]
    return x_train, y_train, x_val, y_val, x_test, y_test


def build_raw_features(x):
    x = np.asarray(x, dtype=np.float32)
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


def target_to_return(x, y):
    last = np.clip(x[:, -1:], 1e-6, None)
    return (y / last - 1.0).astype(np.float32)


def standardize_train(features, target_returns):
    feature_mean = features.mean(axis=0, keepdims=True)
    feature_std = features.std(axis=0, keepdims=True)
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


def compute_metrics(pred, y):
    pred = np.asarray(pred, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    mae = float(np.mean(np.abs(pred - y)))
    mape = float(np.mean(np.abs(pred - y) / np.clip(np.abs(y), 1e-6, None)))
    return {"mae": mae, "mape": mape}


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


class LSTMNet(nn.Module):
    def __init__(self, hidden_size=32):
        super().__init__()
        self.rnn = nn.LSTM(input_size=1, hidden_size=hidden_size, batch_first=True)
        self.head = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        if x.dim() == 2:
            x = x.unsqueeze(-1)
        out, _ = self.rnn(x)
        return self.head(out[:, -1, :])


def make_loader(x, y, batch_size=128, shuffle=False):
    ds = TensorDataset(torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.float32))
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle)


def predict_model(model, x_scaled, device):
    model.eval()
    preds = []
    loader = DataLoader(torch.tensor(x_scaled, dtype=torch.float32), batch_size=512, shuffle=False)
    with torch.no_grad():
        for batch in loader:
            preds.append(model(batch.to(device)).cpu().numpy())
    return np.concatenate(preds, axis=0)


def train_mlp(x_train, y_train, x_val, y_val, x_test, y_test, stats, device):
    feature_mean, feature_std, target_mean, target_std = stats
    input_dim = x_train.shape[1]
    model = MLPNet(input_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.SmoothL1Loss()
    train_loader = make_loader(x_train, y_train, batch_size=128, shuffle=True)

    best_state = None
    best_val_mape = float("inf")
    patience = 80
    stale_epochs = 0
    history = {"train_loss": [], "val_mae": [], "val_mape": [], "test_mae": [], "test_mape": []}

    for epoch in range(1, 1001):
        model.train()
        total_loss = 0.0
        total_count = 0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * len(xb)
            total_count += len(xb)

        val_scaled = predict_model(model, x_val, device)
        test_scaled = predict_model(model, x_test, device)
        val_pred = inverse_prediction(val_scaled, x_val_raw, target_mean, target_std)
        test_pred = inverse_prediction(test_scaled, x_test_raw, target_mean, target_std)
        val_metrics = compute_metrics(val_pred, y_val_raw)
        test_metrics = compute_metrics(test_pred, y_test_raw)

        history["train_loss"].append(total_loss / total_count)
        history["val_mae"].append(val_metrics["mae"])
        history["val_mape"].append(val_metrics["mape"])
        history["test_mae"].append(test_metrics["mae"])
        history["test_mape"].append(test_metrics["mape"])

        if val_metrics["mape"] < best_val_mape:
            best_val_mape = val_metrics["mape"]
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale_epochs = 0
        else:
            stale_epochs += 1

        if epoch == 1 or epoch % 50 == 0:
            print(
                f"epoch {epoch:04d} loss={history['train_loss'][-1]:.6f} "
                f"val_mae={val_metrics['mae']:.6f} val_mape={val_metrics['mape']:.6f} "
                f"test_mae={test_metrics['mae']:.6f} test_mape={test_metrics['mape']:.6f}"
            )

        if stale_epochs >= patience:
            print(f"early stopping at epoch {epoch}, best val_mape={best_val_mape:.6f}")
            break

    model.load_state_dict(best_state)
    return model, history


def choose_blend_alpha(model, x_val, y_val, stats, device):
    _, _, target_mean, target_std = stats
    model_scaled = predict_model(model, x_val, device)
    model_pred = inverse_prediction(model_scaled, x_val_raw, target_mean, target_std)
    last_price = x_val_raw[:, -1:]
    best_alpha = 1.0
    best_metrics = None
    for alpha in [0.0, 0.25, 0.5, 0.75, 1.0]:
        blended = alpha * model_pred + (1.0 - alpha) * last_price
        metrics = compute_metrics(blended, y_val_raw)
        if best_metrics is None or metrics["mape"] < best_metrics["mape"]:
            best_alpha = alpha
            best_metrics = metrics
    return best_alpha, best_metrics


def plot_training_curves(history):
    RESULTS_DIR.mkdir(exist_ok=True)
    epochs = np.arange(1, len(history["train_loss"]) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].plot(epochs, history["train_loss"], label="train_loss")
    axes[0].set_title("Training Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(epochs, history["val_mape"], label="val_mape")
    axes[1].plot(epochs, history["test_mape"], label="test_mape")
    axes[1].set_title("MAPE")
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
    ax.plot(pred[:n].reshape(-1), label="prediction")
    ax.set_title("Test Predictions")
    ax.set_xlabel("Test Sample")
    ax.set_ylabel("Close Price")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(PREDICTION_PLOT_PATH, dpi=160)
    plt.close(fig)


def main():
    seed_everything(42)
    RESULTS_DIR.mkdir(exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    data = np.load(DATA_PATH)
    x_raw, y_raw = make_windows(data)
    global x_val_raw, y_val_raw, x_test_raw, y_test_raw
    x_train_raw, y_train_raw, x_val_raw, y_val_raw, x_test_raw, y_test_raw = time_split(x_raw, y_raw)

    train_features = build_raw_features(x_train_raw)
    val_features = build_raw_features(x_val_raw)
    test_features = build_raw_features(x_test_raw)
    train_target_returns = target_to_return(x_train_raw, y_train_raw)
    val_target_returns = target_to_return(x_val_raw, y_val_raw)
    test_target_returns = target_to_return(x_test_raw, y_test_raw)

    stats = standardize_train(train_features, train_target_returns)
    x_train, y_train = apply_standardization(train_features, train_target_returns, stats)
    x_val, y_val = apply_standardization(val_features, val_target_returns, stats)
    x_test, y_test = apply_standardization(test_features, test_target_returns, stats)

    baseline_val = compute_metrics(x_val_raw[:, -1:], y_val_raw)
    baseline_test = compute_metrics(x_test_raw[:, -1:], y_test_raw)
    print(f"baseline val:  mae={baseline_val['mae']:.6f}, mape={baseline_val['mape']:.6f}")
    print(f"baseline test: mae={baseline_test['mae']:.6f}, mape={baseline_test['mape']:.6f}")

    model, history = train_mlp(x_train, y_train, x_val, y_val, x_test, y_test, stats, device)
    blend_alpha, blend_val = choose_blend_alpha(model, x_val, y_val, stats, device)

    feature_mean, feature_std, target_mean, target_std = stats
    test_scaled = predict_model(model, x_test, device)
    model_test_pred = inverse_prediction(test_scaled, x_test_raw, target_mean, target_std)
    final_test_pred = blend_alpha * model_test_pred + (1.0 - blend_alpha) * x_test_raw[:, -1:]
    model_test = compute_metrics(model_test_pred, y_test_raw)
    final_test = compute_metrics(final_test_pred, y_test_raw)

    print(f"chosen blend_alpha={blend_alpha:.2f}")
    print(f"mlp test:   mae={model_test['mae']:.6f}, mape={model_test['mape']:.6f}")
    print(f"final test: mae={final_test['mae']:.6f}, mape={final_test['mape']:.6f}")

    plot_training_curves(history)
    plot_test_predictions(final_test_pred, y_test_raw)

    checkpoint = {
        "model_type": "mlp",
        "model_state_dict": model.cpu().state_dict(),
        "input_dim": int(x_train.shape[1]),
        "window_size": WINDOW_SIZE,
        "feature_mean": torch.tensor(feature_mean, dtype=torch.float32),
        "feature_std": torch.tensor(feature_std, dtype=torch.float32),
        "target_mean": torch.tensor(target_mean, dtype=torch.float32),
        "target_std": torch.tensor(target_std, dtype=torch.float32),
        "blend_alpha": float(blend_alpha),
    }
    torch.save(checkpoint, MODEL_PATH)

    metrics = {
        "baseline_val": baseline_val,
        "baseline_test": baseline_test,
        "blend_val": blend_val,
        "mlp_test": model_test,
        "final_test": final_test,
        "blend_alpha": float(blend_alpha),
        "epochs": len(history["train_loss"]),
        "artifacts": {
            "model": str(MODEL_PATH),
            "training_curves": str(CURVE_PATH),
            "test_predictions": str(PREDICTION_PLOT_PATH),
        },
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
