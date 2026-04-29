try:
    import spidev
    spi = spidev.SpiDev()
    spi.open(0, 0)  # bus 0, CE0
    spi.max_speed_hz = 1350000
    SPI_AVAILABLE = True
except Exception:
    # Mock SPI for non-hardware/dev environments
    SPI_AVAILABLE = False
    class _MockSpi:
        def xfer2(self, msg):
            # Return a harmless zeroed response
            return [0, 0, 0]
    spi = _MockSpi()

def read_channel(channel):
    if channel < 0 or channel > 3:
        return 0

    cmd = 0b11 << 6              # start + single-ended
    cmd |= (channel & 0x07) << 3

    result = spi.xfer2([cmd, 0, 0])

    value = ((result[1] & 0x0F) << 8) | result[2]
    return value  # 0–4095