# Safety scope and device compatibility

## What the program can write

The runtime accepts exactly one USB device matching `VID 345F / PID 9132` and
validates both interfaces used by the captured display protocol:

- interface 0 must be HID (`0x03`);
- interface 3 must be vendor-specific (`0xFF`);
- endpoint `0x04` must be Bulk OUT.

Image data must have the verified 460,816-byte frame size, header, and trailer.
HID writes are restricted at runtime to a fixed allowlist constructed from:

- the ordinary MythCool display startup capture;
- the four observed display-enable reports;
- the observed display heartbeat.

There is no user-facing raw USB or raw HID command facility.

## Cooling controls deliberately excluded

The project contains no pump, fan, PWM, RPM, motherboard, `hwmon`, or firmware
upgrade implementation. It never accesses USB audio interfaces 1 or 2, never
claims an interface other than display interface 3, and never issues a USB
device reset.

The inspected `345F:9132` descriptor identifies a MacroSilicon `USB Display`
device with HID, audio, and vendor-specific display interfaces; it exposes no
separate pump/fan interface. This is strong evidence that pump and radiator-fan
control are outside this USB display function.

## Same-model devices

USB bus number, device address, physical port chain, Windows device path, and
serial number are intentionally not hard-coded. A deployment discovers a unit
from VID/PID and then validates its interface/endpoint layout, so one compatible
B360GT unit on another computer is selected automatically.

Zero matches produce a clear not-found error. More than one simultaneous match
is rejected as ambiguous instead of choosing an arbitrary device.

## Residual risks

No reverse-engineered hardware protocol can honestly be guaranteed to have
zero risk. The remaining risks are limited primarily to the display function:

- screen blanking, freezing, or returning to the built-in logo after a USB or
  process error;
- contention if MythCool and this program access the display concurrently;
- ordinary display aging or image retention from long-running static content;
- incompatibility if a later B360GT hardware revision reuses the same VID/PID
  but changes its undocumented controller protocol.

The software does not flash firmware. A display-controller hang should normally
recover after stopping the program or power-cycling the computer, but this is
not a manufacturer guarantee.
