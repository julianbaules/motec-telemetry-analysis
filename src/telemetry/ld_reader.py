"""Reader for MoTeC i2 log files (.ld).

The .ld format is not publicly documented. The layout used here follows the
reverse-engineering work of the open-source project "ldparser"
(https://github.com/gotzl/ldparser). This reader re-implements only what the
analysis needs: session metadata and every channel as a NumPy array.

File layout (all integers little-endian):
    header        fixed-size block at offset 0 (pointers + session strings)
    event block   event name, session type, comment, pointer to venue block
    channel list  doubly linked list of channel descriptors
    data          raw samples, one contiguous block per channel
"""
import struct
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# struct format strings: "<" little-endian, I uint32, H uint16, h int16,
# "Ns" N-byte string, "Nx" N padding bytes that are skipped.
HEADER_FMT = "<I4xII20xI24xHHHI8sHHI4x16s16x16s16x64s64s64x64s64x1024xI66x64s126x"
CHANNEL_FMT = "<IIIIHHHHhhhh32s8s12s40x"
EVENT_FMT = "<64s64s1024sH"
VENUE_FMT = "<64s1034xH"
VEHICLE_FMT = "<64s128xI32s32s"


def _decode(raw_bytes: bytes) -> str:
    """Turn a zero-padded byte string into a clean Python string."""
    return raw_bytes.decode("latin-1").split("\x00")[0].strip()


@dataclass
class Channel:
    name: str
    short_name: str
    unit: str
    freq: int                        # sampling frequency in Hz
    data: np.ndarray = field(repr=False)


@dataclass
class LdFile:
    meta: dict
    channels: dict                   # channel name -> Channel

    def to_dataframe(self, freq=None) -> pd.DataFrame:
        """All channels sampled at `freq` in one DataFrame, plus a Time column.

        If `freq` is not given, the most common channel frequency is used.
        """
        freqs = [c.freq for c in self.channels.values()]
        if freq is None:
            freq = max(set(freqs), key=freqs.count)
        columns = {name: c.data for name, c in self.channels.items() if c.freq == freq}
        n_samples = min(len(values) for values in columns.values())
        df = pd.DataFrame({name: values[:n_samples] for name, values in columns.items()})
        df.insert(0, "Time", np.arange(n_samples) / freq)
        return df

    def units(self) -> dict:
        return {name: c.unit for name, c in self.channels.items()}


def _numpy_type(dtype_a: int, dtype: int):
    """Map the two type codes of a channel descriptor to a NumPy type."""
    if dtype_a == 0x07:                       # floating point
        return {2: np.float16, 4: np.float32}.get(dtype)
    if dtype_a in (0x00, 0x03, 0x05):         # signed integer
        return {2: np.int16, 4: np.int32}.get(dtype)
    return None


def read_ld(path) -> LdFile:
    """Read a MoTeC .ld file and return its metadata and channels."""
    with open(path, "rb") as f:
        raw = f.read()

    # 1. Header
    header = struct.unpack_from(HEADER_FMT, raw, 0)
    first_channel_ptr = header[1]
    event_ptr = header[3]
    meta = {
        "date": _decode(header[12]),
        "time": _decode(header[13]),
        "driver": _decode(header[14]),
        "vehicle_id": _decode(header[15]),
        "venue": _decode(header[16]),
        "short_comment": _decode(header[18]),
        "n_channels": header[11],
    }

    # 2. Event, venue and vehicle blocks (chained by pointers)
    if event_ptr:
        event = struct.unpack_from(EVENT_FMT, raw, event_ptr)
        meta["event"] = _decode(event[0])
        meta["session"] = _decode(event[1])
        meta["comment"] = _decode(event[2])
        venue_ptr = event[3]
        if venue_ptr:
            venue = struct.unpack_from(VENUE_FMT, raw, venue_ptr)
            vehicle_ptr = venue[1]
            if vehicle_ptr:
                vehicle = struct.unpack_from(VEHICLE_FMT, raw, vehicle_ptr)
                meta["vehicle_type"] = _decode(vehicle[2])

    # 3. Channels: walk the linked list until the "next" pointer is 0
    channels = {}
    ptr = first_channel_ptr
    while ptr:
        (_prev, next_ptr, data_ptr, n_samples, _counter, dtype_a, dtype, freq,
         shift, mul, scale, dec_places, name, short_name, unit) = struct.unpack_from(
            CHANNEL_FMT, raw, ptr)
        np_type = _numpy_type(dtype_a, dtype)
        if np_type is not None and n_samples > 0:
            values = np.frombuffer(raw, dtype=np_type, count=n_samples, offset=data_ptr)
            # Integer channels are stored scaled; this conversion gives physical units.
            values = (values.astype(np.float64) / (scale or 1) * 10.0 ** -dec_places + shift) * mul
            channel_name = _decode(name)
            channels[channel_name] = Channel(channel_name, _decode(short_name),
                                             _decode(unit), freq, values)
        ptr = next_ptr

    return LdFile(meta, channels)
