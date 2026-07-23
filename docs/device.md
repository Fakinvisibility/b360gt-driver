# Valkyrie B360GT USB display

Information below was distilled from a local USB descriptor report. The raw
machine report is intentionally not distributed because it contains device
serial numbers and unrelated host hardware identifiers.

## Device identity

- Vendor: MacroSilicon Technology Co., Ltd.
- VID: `0x345F`
- PID: `0x9132`
- Manufacturer string: `USB Display `
- Product string: `usb extscreen`
- USB version and speed: USB 2.0 High-Speed (480 Mbit/s)
- USB addresses and port chains are dynamic and must not be hard-coded.
- Device serial numbers are intentionally not used for matching.

## Active high-speed configuration

### Interface 0

- Class: HID (`0x03`)
- Vendor-defined usage page: `0xFF00`
- Endpoint: `0x81`, Interrupt IN
- Maximum packet: 4 bytes
- Feature report length: 9 bytes

This is the control/status interface. The normal MythCool startup report
sequence has been captured and successfully replayed through HIDAPI.

### Interface 3

- Class: Vendor Specific (`0xFF`)
- Interface string: `msusb video`
- Windows driver: `libusb0.sys`
- Endpoint: `0x04`, Bulk OUT
- Maximum packet: 512 bytes

This is the only active high-bandwidth output endpoint and is the expected image/video
transport.

## Safety boundary

The implementation opens only VID/PID `345F:9132`, uses HID interface 0 only
for the verified normal startup/display heartbeat reports, and claims only
interface 3 for image data. It does not access unrelated interfaces, perform
USB resets, or replay firmware-upgrade traffic.

The numeric prefix in UsbTreeView's port chain does not map to the numeric
suffix of a USBPcap interface. The capture interface was verified by capturing
the injected USB device descriptor and matching VID/PID `345F:9132`.
