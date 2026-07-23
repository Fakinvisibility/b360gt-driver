# Display protocol findings

Status: static-image replay verified on physical hardware.

## Transport

- USB VID/PID: `345F:9132`
- Interface: `3` (`0xFF`, vendor specific)
- Endpoint: `0x04`, Bulk OUT
- Maximum USB packet size: 512 bytes
- Windows capture interface on the research machine: `USBPcap4`

USB device addresses are dynamic and must not be hard-coded.

## Frame stream

A complete frame in the captured continuous stream is exactly 460,816 bytes:

| Offset | Length | Meaning |
| ---: | ---: | --- |
| 0 | 8 | `FF 00 00 00 00 1E 01 E0` |
| 8 | 460,800 | 480 × 480 UYVY (YUV 4:2:2) pixel payload |
| 460,808 | 8 | `FF C0 00 00 00 00 00 00` |

Observed frames are contiguous, so the next frame header immediately follows the
previous frame trailer.

The geometry is 480 × 480. The `0x01E0` field in the header is consistent with
the width/height (480), while `0x1E` is consistent with a 30 FPS rate. The frame
rate meaning remains a hypothesis until tested independently.

The payload is UYVY / YUV 4:2:2, two bytes per pixel, and is not JPEG or H.264.
A pure-red capture repeats `5A 51 EF 51`, corresponding to U=90, Y=81, V=239,
Y=81 in BT.601 limited-range encoding.

## Display initialization

The controller uses HID feature reports on interface 0 in addition to the Bulk
frame stream on interface 3:

- `SET_REPORT`: `bmRequestType=0x21`, `bRequest=0x09`,
  `wValue=0x0300`, 8 payload bytes;
- `GET_REPORT`: `bmRequestType=0xA1`, `bRequest=0x01`,
  `wValue=0x0300`, response length 8;
- Windows HIDAPI buffers include a leading report ID byte of zero.

The implementation replays only the 81 reports observed before the first frame
during an ordinary MythCool startup. After the first frame, it sends the four
observed display-enable reports and continues the `B5 00 32 00 00 00 00 00`
heartbeat approximately every 500 ms.

This sequence plus continuous frame streaming has displayed the generated
orientation test image successfully on the physical B360GT. A 15-second test
completed at 20 FPS without a USB error. When streaming stops, the controller
briefly blanks and returns to its built-in Valkyrie logo.

## Capture caveat

Wireshark/TShark captures through USBPcap used a 65,535-byte snapshot limit. A
65,536-byte URB therefore lost 28 payload bytes after accounting for the USBPcap
pseudo-header, or 196 bytes per frame across seven large URBs.

Use `USBPcapCMD.exe` with a snapshot length of at least 262,144 bytes for protocol
evidence intended for replay:

```text
USBPcapCMD.exe -d \\.\USBPcap4 -o capture.pcap -s 262144 -A --inject-descriptors
```

The verified full capture contained:

- seven 65,536-byte payload records per frame;
- one 2,064-byte payload record per frame;
- total: `7 × 65,536 + 2,064 = 460,816` bytes.
