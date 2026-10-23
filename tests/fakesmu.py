"""A fake ryzen_smu device: PM table and mailbox commands behave like a Vermeer CPU."""
import struct

from rankine.tuned import ryzen


class FakeSmu(ryzen.RyzenSmu):
    def __init__(self, version=0x380805, co_readable=True, cores=16):
        super().__init__(path="/nonexistent", ccds=[list(range(i, i + 8)) for i in range(0, cores, 8)])
        self.version = version
        self.co_readable = co_readable
        self.limits = {"ppt": 142.0, "tdc": 95.0, "edc": 140.0}
        self.co = {c: 0 for c in self.all_cores}
        self.log = []

    @property
    def available(self):
        return True

    def codename(self):
        return ryzen.VERMEER

    def table_version(self):
        return self.version

    def _pm_raw(self):
        layout = ryzen.LAYOUTS[self.version]
        values = [0.0] * 600
        values[layout["ppt_limit"]], values[layout["ppt"]] = self.limits["ppt"], 60.0
        values[layout["tdc_limit"]], values[layout["tdc"]] = self.limits["tdc"], 40.0
        values[layout["edc_limit"]], values[layout["edc"]] = self.limits["edc"], 70.0
        for i in range(layout["cores"]):
            values[layout["core_voltage"] + i] = 1.2 + self.co[self.all_cores[i]] * 0.003
            values[layout["core_power"] + i] = 4.0
            values[layout["core_freq"] + i] = 4.5
            values[layout["core_c0"] + i] = 50.0
        return struct.pack(f"<{len(values)}f", *values)

    def _mask_core(self, mask):
        ccd, index = mask >> 28, (mask >> 20) & 0xF
        return self.ccds[ccd][index]

    def _command(self, mailbox, command, args):
        self.log.append((mailbox, command, args[0]))
        if mailbox == "rsmu" and command in (ryzen.RSMU_SET_PPT, ryzen.RSMU_SET_TDC, ryzen.RSMU_SET_EDC):
            key = {ryzen.RSMU_SET_PPT: "ppt", ryzen.RSMU_SET_TDC: "tdc", ryzen.RSMU_SET_EDC: "edc"}[command]
            self.limits[key] = args[0] / 1000
            return 0x01, [0] * 6
        if mailbox == "rsmu" and command == ryzen.RSMU_GET_CO:
            if not self.co_readable:
                return 0xFE, [0] * 6
            return 0x01, [self.co[self._mask_core(args[0])] & 0xFFFF] + [0] * 5
        if mailbox == "mp1" and command == ryzen.MP1_SET_CO:
            margin = args[0] & 0xFFFF
            self.co[self._mask_core(args[0] & 0xFFF00000)] = margin - 0x10000 if margin & 0x8000 else margin
            return 0x01, [0] * 6
        return 0xFE, [0] * 6
