import QtQuick
import QtQuick.Layouts

ControlTile {
    id: root
    property var cpu: ({})
    readonly property var limits: cpu.limits || ({})
    readonly property var ranges: cpu.ranges || ({ ppt: [0, 1], tdc: [0, 1], edc: [0, 1] })
    readonly property var boot: cpu.boot || ({})
    readonly property bool dirty: ppt.dirty || tdc.dirty || edc.dirty
    readonly property bool raised: ppt.shown > (boot.ppt || Infinity) + 0.5 || tdc.shown > (boot.tdc || Infinity) + 0.5
                                   || edc.shown > (boot.edc || Infinity) + 0.5

    title: "Power limits (PBO)"
    status: Math.round(limits.ppt || 0) + " W · " + Math.round(limits.tdc || 0) + " A · " + Math.round(limits.edc || 0) + " A"
    statusColor: Theme.mint

    ValueSlider {
        id: ppt
        label: "PPT, package power"
        unit: "W"
        from: root.ranges.ppt[0]; to: root.ranges.ppt[1]
        value: root.limits.ppt || 0
        defaultValue: root.boot.ppt ?? NaN
    }
    ValueSlider {
        id: tdc
        label: "TDC, sustained current"
        unit: "A"
        from: root.ranges.tdc[0]; to: root.ranges.tdc[1]
        value: root.limits.tdc || 0
        defaultValue: root.boot.tdc ?? NaN
    }
    ValueSlider {
        id: edc
        label: "EDC, peak current"
        unit: "A"
        from: root.ranges.edc[0]; to: root.ranges.edc[1]
        value: root.limits.edc || 0
        defaultValue: root.boot.edc ?? NaN
        hint: "Defaults are the limits at boot, from your BIOS. Lower limits trade some multi-core speed for less power and heat."
    }
    Text {
        visible: root.raised
        text: "Above the boot limits: more power and heat, and the cooler has to keep up. Run a stability test."
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
            visible: Math.round(ppt.shown) !== Math.round(ppt.defaultValue) || Math.round(tdc.shown) !== Math.round(tdc.defaultValue)
                     || Math.round(edc.shown) !== Math.round(edc.defaultValue)
            onClicked: { ppt.target = ppt.defaultValue; tdc.target = tdc.defaultValue; edc.target = edc.defaultValue }
        }
        PillButton {
            text: "Cancel"
            visible: root.dirty
            onClicked: { ppt.target = NaN; tdc.target = NaN; edc.target = NaN }
        }
        PillButton {
            text: "Apply"
            outlined: true
            accent: Theme.mint
            visible: root.dirty
            onClicked: {
                const v = {}
                if (ppt.dirty) v.ppt = Math.round(ppt.target)
                if (tdc.dirty) v.tdc = Math.round(tdc.target)
                if (edc.dirty) v.edc = Math.round(edc.target)
                tuner.setCpuLimits(v)
            }
        }
    }
}
