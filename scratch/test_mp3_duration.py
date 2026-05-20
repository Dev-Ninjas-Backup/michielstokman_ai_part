def get_mp3_duration(data: bytes) -> float:
    try:
        size = len(data)
        i = 0
        if data.startswith(b"ID3") and size >= 10:
            tag_size = (
                (data[6] & 0x7F) << 21
                | (data[7] & 0x7F) << 14
                | (data[8] & 0x7F) << 7
                | (data[9] & 0x7F)
            )
            i = 10 + tag_size
            if i >= size:
                return 0.0

        total_duration = 0.0
        while i < size - 4:
            if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
                header = data[i:i+4]
                ver_bits = (header[1] & 0x18) >> 3
                if ver_bits == 3:
                    ver = 1
                elif ver_bits == 2:
                    ver = 2
                elif ver_bits == 0:
                    ver = 2.5
                else:
                    i += 1
                    continue

                layer = (header[1] & 0x06) >> 1
                if layer != 1:  # Layer III is 1 (0b01)
                    i += 1
                    continue

                bitrate_idx = (header[2] & 0xF0) >> 4
                if bitrate_idx == 0 or bitrate_idx == 15:
                    i += 1
                    continue

                samplerate_idx = (header[2] & 0x0C) >> 2
                if samplerate_idx == 3:
                    i += 1
                    continue

                padding = (header[2] & 0x02) >> 1

                if ver == 1:
                    bitrates = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, -1]
                    samplerates = [44100, 48000, 32000, -1]
                    samples_per_frame = 1152
                else:
                    bitrates = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, -1]
                    if ver == 2:
                        samplerates = [22050, 24000, 16000, -1]
                    else:
                        samplerates = [11025, 12000, 8000, -1]
                    samples_per_frame = 576

                bitrate = bitrates[bitrate_idx] * 1000
                samplerate = samplerates[samplerate_idx]

                if bitrate <= 0 or samplerate <= 0:
                    i += 1
                    continue

                frame_size = int((samples_per_frame // 8) * bitrate // samplerate + padding)
                if frame_size <= 0:
                    i += 1
                    continue

                total_duration += samples_per_frame / samplerate
                i += frame_size
            else:
                i += 1
        return total_duration
    except Exception:
        return 0.0

# Mock test with empty ID3 tag
print("Mock MP3 Duration:", get_mp3_duration(b"ID3\x04\x00\x00\x00\x00\x00\x00"))
