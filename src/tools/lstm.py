from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

try:
    import torch
    from torch import nn

    TORCH_IMPORT_ERROR = None
except Exception as exc:
    torch = None
    nn = None
    TORCH_IMPORT_ERROR = exc


if nn is not None:

    class LSTMNet(nn.Module):
        def __init__(self, input_size=2, hidden_size=48, num_layers=1, dropout=0.1):
            super().__init__()
            rnn_dropout = dropout if num_layers > 1 else 0.0
            self.rnn = nn.LSTM(input_size, hidden_size, num_layers, dropout=rnn_dropout, batch_first=True)
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

else:

    class LSTMNet:
        pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "lstm_training" / "lstm_model.pt"


class LSTMPredictor:
    def __init__(self, model_path: str | Path = DEFAULT_MODEL_PATH):
        self.model_path = Path(model_path)
        self._checkpoint = None
        self._model = None
        self.last_error: Optional[str] = None

    def predict_return(self, last_14_close: np.ndarray) -> Optional[float]:
        self.last_error = None
        if len(last_14_close) < 14 or not self.model_path.exists() or torch is None:
            if torch is None and TORCH_IMPORT_ERROR is not None:
                self.last_error = str(TORCH_IMPORT_ERROR)
            return None
        try:
            checkpoint = self._load_checkpoint()
            if checkpoint.get("model_type") != "lstm":
                self.last_error = f"unsupported model_type: {checkpoint.get('model_type')}"
                return None
            model = self._load_model(checkpoint)
            close = last_14_close.astype(np.float32)
            features = self._build_features(close, int(checkpoint.get("input_size", 2)))
            x_scaled = (features - checkpoint["feature_mean"].numpy()) / checkpoint["feature_std"].numpy()
            with torch.no_grad():
                pred_scaled = model(torch.tensor(x_scaled, dtype=torch.float32)).numpy()
            pred_return = pred_scaled * checkpoint["target_std"].numpy() + checkpoint["target_mean"].numpy()
            alpha = float(checkpoint.get("alpha", 1.0))
            return float((alpha * pred_return).reshape(-1)[0])
        except Exception as exc:
            self.last_error = str(exc)
            return None

    def _build_features(self, close: np.ndarray, input_size: int) -> np.ndarray:
        x = close.reshape(1, -1).astype(np.float32)
        last = np.clip(x[:, -1:], 1e-6, None)
        relative_price = x / last - 1.0

        returns = np.zeros_like(x, dtype=np.float32)
        returns[:, 1:] = x[:, 1:] / np.clip(x[:, :-1], 1e-6, None) - 1.0
        if input_size == 2:
            return np.stack([relative_price, returns], axis=2).astype(np.float32)

        ma3_deviation = np.zeros_like(x, dtype=np.float32)
        ma5_deviation = np.zeros_like(x, dtype=np.float32)
        std3 = np.zeros_like(x, dtype=np.float32)
        std5 = np.zeros_like(x, dtype=np.float32)
        for index in range(x.shape[1]):
            price_window_3 = x[:, max(0, index - 2) : index + 1]
            price_window_5 = x[:, max(0, index - 4) : index + 1]
            return_window_3 = returns[:, max(0, index - 2) : index + 1]
            return_window_5 = returns[:, max(0, index - 4) : index + 1]
            ma3 = price_window_3.mean(axis=1)
            ma5 = price_window_5.mean(axis=1)
            ma3_deviation[:, index] = x[:, index] / np.clip(ma3, 1e-6, None) - 1.0
            ma5_deviation[:, index] = x[:, index] / np.clip(ma5, 1e-6, None) - 1.0
            std3[:, index] = return_window_3.std(axis=1)
            std5[:, index] = return_window_5.std(axis=1)

        low = x.min(axis=1, keepdims=True)
        high = x.max(axis=1, keepdims=True)
        price_position = (x - low) / np.clip(high - low, 1e-6, None)
        features = np.stack(
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
        if features.shape[-1] != input_size:
            raise ValueError(f"unsupported input_size: {input_size}")
        return features

    def _load_checkpoint(self):
        if self._checkpoint is None:
            self._checkpoint = torch.load(self.model_path, map_location="cpu")
        return self._checkpoint

    def _load_model(self, checkpoint):
        if self._model is None:
            self._model = LSTMNet(
                input_size=int(checkpoint.get("input_size", 2)),
                hidden_size=int(checkpoint.get("hidden_size", 48)),
                num_layers=int(checkpoint.get("num_layers", 1)),
                dropout=float(checkpoint.get("dropout", 0.1)),
            )
            self._model.load_state_dict(checkpoint["model_state_dict"])
            self._model.eval()
        return self._model
