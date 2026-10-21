# Model sources and checksums

FaceRec downloads these unmodified OpenCV Zoo models during lab installation:

| Model | Source | License | Pinned SHA-256 |
|---|---|---|---|
| YuNet `face_detection_yunet_2023mar.onnx` | <https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet> | MIT | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| SFace `face_recognition_sface_2021dec.onnx` | <https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface> | Apache 2.0 | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` |

`scripts/download_models.sh` rejects files that do not match these pinned checksums.

