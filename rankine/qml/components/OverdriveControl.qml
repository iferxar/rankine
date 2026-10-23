import QtQuick
import QtQuick.Layouts

ControlTile {
    id: root
    property string card
    property var od: ({})
    property real peakVoltage: NaN  // highest GPU voltage seen this session, in mV
    readonly property var boot: od.boot || ({})
    readonly property var range: od.range || ({})
    readonly property bool dirty: core.dirty || mem.dirty || volt.dirty
    readonly property bool overclocked: core.shown > (boot.sclk_max || Infinity) || mem.shown > (boot.mclk_max || Infinity)
    readonly property bool undervolted: volt.shown < 0

    function reset() { core.target = NaN; mem.target = NaN; volt.target = NaN }

    title: "Clocks and voltage"
    status: (od.sclk ? od.sclk[od.sclk.length - 1] + " MHz" : "") + (od.voltage_offset !== undefined
            ? " · " + od.voltage_offset + " mV" : "")
    statusColor: Theme.mint

    ValueSlider {
        id: core
        visible: !!root.od.sclk && !!root.range.sclk
        label: "Max core clock"
        unit: "MHz"
        from: root.range.sclk ? Math.max(root.range.sclk[0], root.od.sclk[0] + 1) : 0
        to: root.range.sclk ? root.range.sclk[1] : 1
        value: root.od.sclk ? root.od.sclk[root.od.sclk.length - 1] : 0
        defaultValue: root.boot.sclk_max ?? NaN
        stepSize: 5
        hint: "Same number as the max frequency in Windows tools. Their min frequency is left to the driver here."
    }
    ValueSlider {
        id: mem
        visible: !!root.od.mclk && !!root.range.mclk
        label: "Max memory clock"
        unit: "MHz"
        from: root.range.mclk ? root.range.mclk[0] : 0
        to: root.range.mclk ? root.range.mclk[1] : 1
        value: root.od.mclk ? root.od.mclk[root.od.mclk.length - 1] : 0
        defaultValue: root.boot.mclk_max ?? NaN
        stepSize: 5
        hint: "Windows tools show memory at double rate (" + Math.round(mem.shown) * 2 + " MHz there): "
              + "halve a guide's value, so 2150 MHz is 1075 here."
    }
    ValueSlider {
        id: volt
        visible: root.od.voltage_offset !== undefined
        label: "Voltage offset"
        unit: "mV"
        from: root.od.voltage_range ? root.od.voltage_range[0] : -150
        to: root.od.voltage_range ? root.od.voltage_range[1] : 0
        value: root.od.voltage_offset ?? 0
        defaultValue: root.boot.voltage_offset ?? NaN
        stepSize: 5
        hint: "Linux shifts the whole voltage curve by this offset. Windows guides give a max voltage instead: "
              + "the offset is roughly that value minus the card's stock peak voltage under load."
              + (isNaN(root.peakVoltage) ? "" : " Highest voltage seen this session: "
                 + Math.round(root.peakVoltage) + " mV (with the offset active at the time).")
    }
    Text {
        visible: root.overclocked || root.undervolted
        text: (root.overclocked ? "Above the card's default clocks. " : "")
              + (root.undervolted ? "Undervolting lowers power and heat but can make the GPU hang. " : "")
              + "Go in small steps and run a stability test after each one. "
              + "If the GPU hangs, Rankine puts the original values back."
        color: Theme.amber
        font.family: Theme.fontFamily
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Item { Layout.fillWidth: true }
        PillButton {
            text: "Defaults"
            visible: Math.round(core.shown) !== Math.round(core.defaultValue)
                     || Math.round(mem.shown) !== Math.round(mem.defaultValue)
                     || Math.round(volt.shown) !== Math.round(volt.defaultValue)
            onClicked: { core.target = core.defaultValue; mem.target = mem.defaultValue; volt.target = volt.defaultValue }
        }
        PillButton {
            text: "Cancel"
            visible: root.dirty
            onClicked: root.reset()
        }
        PillButton {
            text: "Apply"
            outlined: true
            accent: Theme.mint
            visible: root.dirty
            onClicked: {
                const values = {}
                if (core.dirty) values.sclk_max = Math.round(core.target)
                if (mem.dirty) values.mclk_max = Math.round(mem.target)
                if (volt.dirty) values.voltage_offset = Math.round(volt.target)
                tuner.setOverdrive(root.card, values)
            }
        }
    }
}
