import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

// What Rankine can tune on this machine; live GPU controls when rankine-tuned is running.
ScrollView {
    id: page
    contentWidth: availableWidth

    readonly property var t: tuner.report
    readonly property var helper: t.helper || ({})
    readonly property var cards: (tuner.state.cards) || ({})
    readonly property var helperFeature: helper.running
        ? { title: "Helper service", state: "ready",
            detail: "rankine-tuned is running on the " + helper.bus + " bus. Every change asks for your password, "
                    + "and reverts after a few seconds unless you keep it." }
        : helper.installed
        ? { title: "Helper service", state: "setup",
            detail: "rankine-tuned is installed but not running. This page works without it; tuning will need it.",
            command: "sudo systemctl enable --now rankine-tuned.service" }
        : { title: "Helper service", state: "setup",
            detail: "rankine-tuned is not installed. This page works without it; tuning will need it.",
            fix: "From the Rankine checkout, install the system files, then enable the service:",
            command: "sudo ./scripts/install-tuned.sh && sudo systemctl enable --now rankine-tuned.service" }

    Item {
        width: page.availableWidth
        implicitHeight: grid.implicitHeight + 32 + (tuner.state.pending ? 90 : 0)  // room for the toast

        GridLayout {
            id: grid
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
            columns: width > 1000 ? 2 : 1
            columnSpacing: 16
            rowSpacing: 16
            uniformCellWidths: true

            Card {
                title: "Tuning"
                subtitle: page.helper.running ? "CHANGES REVERT UNLESS KEPT" : "READ-ONLY"
                subtitleColor: Theme.amber
                Layout.columnSpan: grid.columns
                Layout.fillWidth: true

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    Text {
                        text: "What Rankine can tune on this machine, and what each feature still needs. "
                            + "Versions refer to the roadmap in docs/TUNING.md. Settings last until reboot or "
                            + "until the helper stops, unless you save them to apply at boot."
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    PillButton { text: "Refresh"; onClicked: tuner.refresh() }
                }
                FeatureRow { feature: page.helperFeature }
                Text {
                    visible: tuner.busy || tuner.message !== ""
                    text: tuner.busy ? "Waiting for authorization…" : "Couldn't apply: " + tuner.message
                    color: tuner.busy ? Theme.amber : Theme.red
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Text {
                    readonly property var last: (tuner.state.faults || []).slice(-1)[0]
                    visible: !!last
                    text: last ? "Last GPU hang, " + new Date(last.time * 1000).toLocaleTimeString(Qt.locale(), "HH:mm:ss")
                                 + ": " + last.text + ". Original clocks, voltage and power were restored." : ""
                    color: Theme.red
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                ComparisonTile {
                    visible: !!tuner.comparison.what
                    comparison: tuner.comparison
                }
            }

            Repeater {
                model: page.t.gpus || []
                delegate: Card {
                    id: gpuCard
                    required property var modelData
                    readonly property var live: page.cards[modelData.card]
                    title: "Graphics"
                    subtitle: modelData.name
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.alignment: Qt.AlignTop

                    PowerControl {
                        visible: !!gpuCard.live && !!gpuCard.live.power
                        card: gpuCard.modelData.card
                        power: gpuCard.live && gpuCard.live.power ? gpuCard.live.power : ({ cap: 0, min: 0, max: 1, default: 0 })
                    }
                    PerformanceControl {
                        visible: !!gpuCard.live && !!gpuCard.live.level
                        card: gpuCard.modelData.card
                        level: gpuCard.live ? gpuCard.live.level || "" : ""
                        profiles: gpuCard.live ? gpuCard.live.profiles : []
                        profile: gpuCard.live && gpuCard.live.profile !== null ? gpuCard.live.profile : -1
                    }
                    FanCurveEditor {
                        visible: !!gpuCard.live && gpuCard.live.fan.percent !== null
                        card: gpuCard.modelData.card
                        fan: gpuCard.live ? gpuCard.live.fan : ({ mode: "auto", curve: null, percent: null })
                        temp: gpuCard.live ? gpuCard.live.temp : null
                    }
                    OverdriveControl {
                        visible: !!gpuCard.live && !!gpuCard.live.overdrive
                        card: gpuCard.modelData.card
                        od: gpuCard.live && gpuCard.live.overdrive ? gpuCard.live.overdrive : ({})
                        peakVoltage: backend.data.stats["gpu.voltage"] ? backend.data.stats["gpu.voltage"].max * 1000 : NaN
                    }
                    StabilityTile {
                        visible: !!gpuCard.live
                        stability: tuner.stability
                        watching: !!tuner.state.fault_watch
                    }
                    BootProfileTile {
                        visible: !!gpuCard.live && !!tuner.state.boot_profile
                        card: gpuCard.modelData.card
                        live: gpuCard.live || ({})
                        profile: tuner.state.boot_profile || ({})
                        tested: !!tuner.tested[gpuCard.modelData.card]
                        pending: !!tuner.state.pending
                    }
                    // Without the helper, or for what it cannot control yet, explain instead.
                    Repeater {
                        id: gpuRows
                        readonly property var rows: gpuCard.modelData.features.filter(f => !gpuCard.live
                            || ["gpu-power", "gpu-profile", "gpu-fan"].indexOf(f.id) < 0
                               && !(f.id === "gpu-overdrive" && gpuCard.live.overdrive))
                        model: rows.length  // count model: rows survive the per-second state refresh
                        delegate: FeatureRow { required property int index; feature: gpuRows.rows[index] }
                    }
                    RowLayout {
                        visible: !!gpuCard.live && gpuCard.live.changed
                        Layout.fillWidth: true
                        Text {
                            text: "Changed by Rankine since the helper started."
                            color: Theme.dim
                            font.family: Theme.fontFamily
                            font.pixelSize: 11
                            Layout.fillWidth: true
                        }
                        PillButton { text: "Restore original settings"; onClicked: tuner.reset(gpuCard.modelData.card) }
                    }
                }
            }

            Card {
                visible: !!page.t.cpu
                title: "Processor"
                subtitle: page.t.cpu ? page.t.cpu.name + (page.t.cpu.codename ? " · " + page.t.cpu.codename : "") : ""
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                CpuReadings {
                    visible: !!tuner.state.cpu
                    table: tuner.state.cpu ? tuner.state.cpu.table : ({})
                }
                CpuLimitsControl {
                    visible: !!tuner.state.cpu && !!tuner.state.cpu.ranges
                    cpu: tuner.state.cpu || ({})
                }
                CurveOptimizerControl {
                    visible: !!tuner.state.cpu
                    cpu: tuner.state.cpu || ({})
                }
                StabilityTile {
                    visible: !!tuner.state.cpu
                    target: "cpu"
                    stability: tuner.stability
                    watching: !!tuner.state.fault_watch
                }
                BootProfileTile {
                    visible: !!tuner.state.cpu && !!tuner.state.boot_profile
                    card: "cpu"
                    live: tuner.state.cpu || ({})
                    profile: tuner.state.boot_profile || ({})
                    tested: !!tuner.tested["cpu"]
                    pending: !!tuner.state.pending
                }
                // Without the helper or the SMU, explain what is missing instead.
                Repeater {
                    id: cpuRows
                    readonly property var rows: page.t.cpu && !tuner.state.cpu ? page.t.cpu.features : []
                    model: rows.length
                    delegate: FeatureRow { required property int index; feature: cpuRows.rows[index] }
                }
            }

            Card {
                visible: (page.t.tools || []).length > 0
                title: "Stability testing"
                subtitle: "TOOLS"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                Repeater {
                    model: page.t.tools || []
                    delegate: FeatureRow { required property var modelData; feature: modelData }
                }
            }
        }
    }
}
