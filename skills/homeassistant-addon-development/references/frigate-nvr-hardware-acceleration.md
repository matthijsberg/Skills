# Frigate NVR: Hardware Acceleration & Intel iGPU Offloading

A reference guide for configuring Frigate NVR with Intel integrated graphics (Intel UHD / Iris Xe / Arc iGPU on Intel Core Ultra / Meteor Lake) to minimize CPU usage and prevent decoding crashes.

---

## 1. Offloading Object Detection to Intel iGPU (OpenVINO)

By default, omitting the `detectors:` block causes Frigate to fall back to the **CPU** (TensorFlow Lite running on host cores), resulting in 80–100% CPU spikes during motion events.

### Recommended Configuration (Intel iGPU)
```yaml
detectors:
  ov:
    type: openvino
    device: GPU  # Routes inference to Intel integrated GPU (Intel UHD / Iris Xe / Arc)
```
- **Performance Impact:** Inference latency drops from ~60–100 ms (CPU) to **8–15 ms (iGPU)**.
- **Hardware Requirement:** Container must have access to `/dev/dri/renderD128` (default in official Home Assistant Frigate Add-on with hardware access enabled).

---

## 2. The Proprietary Codec Trap (`H.265+` / `H.264+` / Smart Codecs)

Many IP cameras (Hikvision, Dahua, Annke) ship with proprietary "Smart Codec" or "H.265+" / "H.264+" enabled by default.

### Pitfall & Symptoms
- **Mechanism:** `H.265+` uses dynamic Group of Pictures (GOP) and skips standard I-frames (keyframes) to reduce bandwidth on static scenes. Hardware decoders (Intel VA-API / QSV) require strictly compliant I-frames and cannot parse this proprietary stream.
- **Cascade of Failures:**
  1. FFmpeg crashes on stream start (`watchdog.<camera> | FFmpeg has exited`).
  2. Recording segments in `/tmp/cache/` are 0-byte or corrupted (`Invalid or missing video stream in segment ... Discarding`).
  3. OpenCV crashes when trying to extract frames (`OpenCV(4.x) error: (-215:Assertion failed) in function 'icvExtractPattern'`).
  4. Cache overflow alert appears: `Too many unprocessed recording segments in cache for <camera>`.
- **Solution:** In the camera's native web management interface under **Video/Audio**, turn **`H.265+: OFF`** (or `Smart Codec: OFF`) and select standard **`H.265`** or **`H.264`**.

---

## 3. Hardware Acceleration Presets (`preset-vaapi` vs `preset-intel-qsv-*`)

### Global vs Per-Camera Overrides
On modern Intel processors (11th Gen Tiger Lake, 12th Gen Alder Lake, 13th/14th Gen Raptor Lake, and Intel Core Ultra Meteor Lake with Arc graphics), use generic **`preset-vaapi`** globally:

```yaml
ffmpeg:
  hwaccel_args: preset-vaapi
```

### Pitfall: Hardcoding `preset-intel-qsv-h265` on Inputs
- **Do not** manually hardcode `hwaccel_args: preset-intel-qsv-h265` on camera inputs unless specifically verified.
- If a camera substream outputs H.264 and is forced into `preset-intel-qsv-h265`, the hardware decoder fails immediately with code 1.
- `preset-vaapi` auto-negotiates both H.264 and H.265 streams transparently in hardware.

---

## 4. Stream Roles & Passthrough Recording

Frigate handles `detect` and `record` roles differently:
- **`detect` role:** Decodes video frames into raw memory buffers for motion analysis and object detection. **Requires hardware acceleration (`preset-vaapi`).**
- **`record` role:** Takes RTSP packets directly from `go2rtc` and writes them to MP4 container segments on disk via stream copy (`-c copy`). **Never decodes video.**

### Rule: Never put `hwaccel_args` on `record`
```yaml
# CORRECT:
inputs:
  - path: rtsp://127.0.0.1:8554/camera_sub
    roles:
      - detect
    input_args: preset-rtsp-restream
  - path: rtsp://127.0.0.1:8554/camera_main
    roles:
      - record
    input_args: preset-rtsp-restream
    # NO hwaccel_args here!
```
Adding `hwaccel_args` to the `record` input forces FFmpeg to needlessly decode 4K/high-res video before saving, creating massive memory bloat and FFmpeg segment errors.

---

## 5. Detection Resolution Alignment & Contrast Optimization

1. **Exact Sizing:** Set `detect.width` and `detect.height` to the **exact native resolution** of the camera's substream (e.g. `1280x720` or `640x360`). Any discrepancy forces FFmpeg to perform software CPU resizing for every single frame.
2. **Disable `improve_contrast`:** Under `motion:`, set `improve_contrast: false`. Setting this to `true` forces an expensive histogram equalization algorithm on the CPU for every frame. Only enable it if low-light nighttime detection fails completely.
