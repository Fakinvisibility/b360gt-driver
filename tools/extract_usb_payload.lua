-- Extract captured USB payload bytes into a contiguous binary stream.
--
-- Environment variables:
--   B360_USB_DEVICE   decimal USB address, default 1
--   B360_USB_ENDPOINT decimal endpoint number, default 4
--   B360_USB_OUTPUT   output path

local device_address = tonumber(os.getenv("B360_USB_DEVICE") or "1")
local endpoint_address = tonumber(os.getenv("B360_USB_ENDPOINT") or "4")
local output_path = os.getenv("B360_USB_OUTPUT") or "captures/bulk_stream.bin"

local usb_device = Field.new("usb.device_address")
local usb_endpoint = Field.new("usb.endpoint_address")
local usb_data = Field.new("usb.data_fragment")
local usb_capdata = Field.new("usb.capdata")

local output = assert(io.open(output_path, "wb"))
local bytes_written = 0
local tap = Listener.new("usb")

function tap.packet()
    local device = usb_device()
    local endpoint = usb_endpoint()
    -- USBPcap stores host-to-device bulk bytes in usb.capdata. Prefer it:
    -- usb.data_fragment can exist as a zero/partial field on some URBs.
    local data = usb_capdata() or usb_data()

    if device ~= nil
        and endpoint ~= nil
        and data ~= nil
        and tonumber(tostring(device)) == device_address
        and tonumber(tostring(endpoint)) == endpoint_address then
        local raw = data.range:bytes():raw()
        output:write(raw)
        bytes_written = bytes_written + #raw
    end
end

function tap.draw()
    output:flush()
    output:close()
    print(string.format(
        "Extracted %d bytes from USB address %d endpoint 0x%02X to %s",
        bytes_written,
        device_address,
        endpoint_address,
        output_path
    ))
end
