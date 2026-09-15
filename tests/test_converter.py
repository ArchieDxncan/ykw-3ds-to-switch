from pathlib import Path
import struct
import unittest

import ykw_3ds_to_switch as ykw


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "switch_fresh_template.yw"
SAMPLE = ROOT.parent / "work" / "extracted" / "3ds alot of playtime.yw"


class ConverterTests(unittest.TestCase):
    def test_bundled_template_is_valid_switch_save(self):
        raw = TEMPLATE.read_bytes()
        self.assertEqual(len(raw), 0xB9CC)
        meta, sections, _ = ykw.parse_container(ykw.decrypt_save(raw, "template"), "template")
        self.assertEqual(len(meta), 0x1A0)
        self.assertEqual(set(sections), {1, 2, 3, 7, 8, 11, 12, 13, 14, 15, 16})

    @unittest.skipUnless(SAMPLE.exists(), "development sample is not distributed")
    def test_sample_round_trip_and_confirmed_fields(self):
        source_raw = SAMPLE.read_bytes()
        result = ykw.convert(source_raw, TEMPLATE.read_bytes(), fresh_seed=False)
        self.assertEqual(len(result), 0xB9CC)
        source = ykw.decrypt_save(source_raw, "source")
        output = ykw.decrypt_save(result, "output")
        source_meta, source_sections, _ = ykw.parse_container(source, "source")
        output_meta, output_sections, _ = ykw.parse_container(output, "output")
        self.assertEqual(output_meta[0x14:0x18], source_meta[0x14:0x18])
        self.assertEqual(output_meta[0x146], source_meta[0x44])
        self.assertEqual(output_meta[0x14C], source_meta[0x44])
        old_ids = [struct.unpack_from("<i", source_sections[7][0], p + 4)[0]
                   for p in range(0, len(source_sections[7][0]), 0x5C)]
        new_ids = [struct.unpack_from("<i", output_sections[7][0], p + 4)[0]
                   for p in range(0, len(output_sections[7][0]), 0x7C)]
        self.assertEqual(old_ids, new_ids)

    def test_bad_crc_is_rejected(self):
        damaged = bytearray(TEMPLATE.read_bytes())
        damaged[100] ^= 1
        with self.assertRaisesRegex(ykw.SaveError, "CRC32"):
            ykw.decrypt_save(bytes(damaged), "damaged")


if __name__ == "__main__":
    unittest.main()
