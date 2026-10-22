import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import "components"

ApplicationWindow {
    id: win
    width: 1180
    height: 820
    minimumWidth: 640
    minimumHeight: 480
    visible: true
    title: "Rankine"
    color: Theme.bg
    font.family: Theme.fontFamily

    readonly property var d: backend.data
    readonly property var cpu: d.cpu
    readonly property var gpu: d.gpu
    readonly property var mem: d.mem
    readonly property var g: gpu || ({})
    function st(key) { return d.stats[key] }
    function statusColor(s) { return s === "COOL" ? Theme.mint : s === "WARM" ? Theme.amber : s === "HOT" ? Theme.red : Theme.muted }

    // Nebula glow behind the cards, echoing the CachyOS space wallpapers.
    background: Rectangle {
        color: Theme.bg
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: win.width * 0.85; centerY: 0
                    centerRadius: win.width * 0.6
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0.0; color: Qt.rgba(0, 0.67, 0.53, 0.16) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                PathRectangle { width: win.width; height: win.height }
            }
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: 0; centerY: win.height
                    centerRadius: win.width * 0.5
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0.0; color: Qt.rgba(0, 0.8, 1, 0.08) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                PathRectangle { width: win.width; height: win.height }
            }
        }
    }

    header: Rectangle {
        color: Theme.bgDeep
        implicitHeight: 58
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Theme.teal }
                GradientStop { position: 0.35; color: Theme.cyan }
                GradientStop { position: 0.7; color: Theme.border }
                GradientStop { position: 1.0; color: Theme.border }
            }
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 16
            spacing: 10

            Facet { size: 20 }
            Text {
                text: "RANKINE"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 17
                font.weight: Font.Bold
                font.letterSpacing: 2.5
            }
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 24
                text: win.cpu.name + (win.gpu ? "  ·  " + win.gpu.name : "")
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 12
                elide: Text.ElideRight
            }
            PillButton {
                text: "●  " + win.d.status
                outlined: true
                accent: win.statusColor(win.d.status)
            }
            PillButton { text: "Reset Stats"; onClicked: backend.resetStats() }
        }
    }

    ScrollView {
        id: scroll
        anchors.fill: parent
        contentWidth: availableWidth

        Item {
            width: scroll.availableWidth
            implicitHeight: grid.implicitHeight + 32

            GridLayout {
                id: grid
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
                columns: width > 1000 ? 2 : 1
                columnSpacing: 16
                rowSpacing: 16
                uniformCellWidths: true

                // ── Processor ──────────────────────────────────────────────
                Card {
                    title: "Processor"
                    subtitle: win.cpu.name
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.alignment: Qt.AlignTop

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12
                        ArcGauge {
                            Layout.preferredWidth: 140; Layout.preferredHeight: 150
                            value: win.cpu.temp ?? 0; minValue: 20; maxValue: 100
                            colors: Theme.tempGradient(win.cpu.temp)
                            valueText: Theme.fmt(win.cpu.temp, 0, "°C")
                            label: "Temp"; coloredLabel: true
                            footer: Theme.range(win.st("cpu.temp"), 0, "°C")
                        }
                        ArcGauge {
                            Layout.preferredWidth: 120; Layout.preferredHeight: 150
                            thickness: 9
                            value: win.cpu.load ?? 0
                            colors: Theme.loadGradient(win.cpu.load)
                            valueText: Theme.fmt(win.cpu.load, 0, "%")
                            label: "Load"
                            footer: Theme.range(win.st("cpu.load"), 0, "%")
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            columns: 2; columnSpacing: 8; rowSpacing: 8
                            Tile {
                                title: "Clock"; value: Theme.fmt(win.cpu.mhz, 0, " MHz")
                                footer: Theme.range(win.st("cpu.mhz"), 0, "", true)
                            }
                            Tile {
                                title: "Power"; value: Theme.fmt(win.cpu.power, 1, " W")
                                footer: win.cpu.power_hint || Theme.range(win.st("cpu.power"), 1, "", true)
                            }
                            Tile {
                                title: "Voltage"; value: Theme.fmt(win.cpu.voltage, 3, " V")
                                estimated: win.cpu.voltage_estimated
                                footer: Theme.range(win.st("cpu.voltage"), 3, "", true)
                            }
                            Tile {
                                title: "Current"; value: Theme.fmt(win.cpu.current, 1, " A")
                                estimated: true
                                footer: win.cpu.power_hint ? "needs CPU power" : Theme.range(win.st("cpu.current"), 1, "", true)
                            }
                        }
                    }

                    Sparkline {
                        labelA: "Temp (°C)"; labelB: "Usage (%)"
                        seriesA: win.d.history["cpu.temp"]; minA: 20; maxA: 100
                        seriesB: win.d.history["cpu.load"]
                    }

                    CoreGrid { cores: win.cpu.cores }
                }

                // ── Graphics ───────────────────────────────────────────────
                Card {
                    title: "Graphics"
                    subtitle: win.gpu ? win.gpu.name : "No supported GPU found"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.alignment: Qt.AlignTop

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12
                        ArcGauge {
                            Layout.preferredWidth: 140; Layout.preferredHeight: 150
                            value: win.g.temp ?? 0; minValue: 20; maxValue: 100
                            colors: Theme.tempGradient(win.g.temp)
                            valueText: Theme.fmt(win.g.temp, 0, "°C")
                            label: "Temp"; coloredLabel: true
                            footer: win.g.hotspot != null
                                    ? "Max " + Theme.fmt((win.st("gpu.temp") || {}).max, 0, "°C") + " · Hotspot " + Theme.fmt(win.g.hotspot, 0, "°C")
                                    : Theme.range(win.st("gpu.temp"), 0, "°C")
                        }
                        ArcGauge {
                            Layout.preferredWidth: 120; Layout.preferredHeight: 150
                            thickness: 9
                            value: win.g.load ?? 0
                            colors: Theme.loadGradient(win.g.load)
                            valueText: Theme.fmt(win.g.load, 0, "%")
                            label: "Core"
                            footer: Theme.range(win.st("gpu.load"), 0, "%")
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            columns: 2; columnSpacing: 8; rowSpacing: 8
                            Tile {
                                title: "Clock"; value: Theme.fmt(win.gpu ? win.gpu.mhz : null, 0, " MHz")
                                footer: Theme.range(win.st("gpu.mhz"), 0, "", true)
                            }
                            Tile {
                                title: "Power"; value: Theme.fmt(win.gpu ? win.gpu.power : null, 1, " W")
                                footer: Theme.range(win.st("gpu.power"), 1, "", true)
                            }
                            Tile {
                                title: "Voltage"; value: Theme.fmt(win.gpu ? win.gpu.voltage : null, 3, " V")
                                footer: Theme.range(win.st("gpu.voltage"), 3, "", true)
                            }
                            Tile {
                                title: "Current"; value: Theme.fmt(win.gpu ? win.gpu.current : null, 1, " A")
                                estimated: true
                                footer: Theme.range(win.st("gpu.current"), 1, "", true)
                            }
                        }
                    }

                    Sparkline {
                        labelA: "Temp (°C)"; labelB: "Core (%)"
                        seriesA: win.d.history["gpu.temp"]; minA: 20; maxA: 100
                        seriesB: win.d.history["gpu.load"]
                    }

                    BarRow {
                        visible: win.gpu && win.gpu.vram_total != null
                        label: "VRAM USAGE"
                        valueText: win.gpu ? Theme.fmt(win.gpu.vram_used, 1, "") + " / " + Theme.fmt(win.gpu.vram_total, 1, " GB") : ""
                        frac: win.gpu && win.gpu.vram_total ? win.gpu.vram_used / win.gpu.vram_total : 0
                        accentText: Theme.fmt(frac * 100, 0, " %")
                    }
                }

                // ── Memory ─────────────────────────────────────────────────
                Card {
                    title: "Memory"
                    subtitle: Theme.fmt(win.mem.used, 1, "") + " / " + Theme.fmt(win.mem.total, 1, " GB") + "   " + Theme.fmt(win.mem.percent, 0, " %")
                    subtitleColor: Theme.cyan
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.alignment: Qt.AlignTop

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 8; radius: 4
                        color: Theme.track
                        Rectangle {
                            height: parent.height; radius: parent.radius
                            width: parent.width * (win.mem.percent ?? 0) / 100
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0.0; color: Theme.teal }
                                GradientStop { position: 1.0; color: Theme.cyan }
                            }
                            Behavior on width { NumberAnimation { duration: 400 } }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Tile {
                            title: "Clock"; value: Theme.fmt(win.mem.clock, 0, " MT/s")
                            footer: win.mem.dimm_hint || "DIMM configured speed"
                        }
                        Tile {
                            title: "Voltage"; value: Theme.fmt(win.mem.voltage, 2, " V")
                            footer: win.mem.dimm_hint || "DIMM configured voltage"
                        }
                        Tile {
                            title: "Temperature"; value: Theme.fmt(win.mem.temp, 1, "°C")
                            footer: win.mem.temp == null ? "no DIMM sensor" : Theme.range(win.st("mem.temp"), 1, "", true)
                        }
                        Tile {
                            title: "Swap"; value: Theme.fmt(win.mem.swap_used, 1, "") + " / " + Theme.fmt(win.mem.swap_total, 0, " GB")
                            footer: Theme.range(win.st("mem.swap_used"), 2, " GB")
                        }
                    }

                    Sparkline {
                        labelA: "Memory Usage (%)"; labelB: ""
                        colorA: Theme.cyan
                        seriesA: win.d.history["mem.percent"]
                    }
                }

                // ── Cooling & drives ───────────────────────────────────────
                Card {
                    title: "Cooling fans"
                    subtitle: "RPM TELEMETRY"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.alignment: Qt.AlignTop

                    Text {
                        visible: win.d.fans.length === 0
                        text: "No fan sensors reported. Motherboard Super I/O drivers (nct6775, nct6687, it87) expose them."
                        color: Theme.muted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Repeater {
                        model: win.d.fans
                        delegate: BarRow {
                            required property var modelData
                            spinner: true
                            spinSpeed: (modelData.rpm || 0) / 1200
                            label: modelData.name
                            valueText: modelData.text
                            frac: modelData.frac
                        }
                    }

                    RowLayout {
                        visible: win.d.drives.length > 0
                        Layout.topMargin: 6
                        spacing: 8
                        Facet { size: 13 }
                        Text {
                            text: "DRIVES"
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: 13
                            font.weight: Font.Bold
                            font.letterSpacing: 1.2
                        }
                    }
                    Repeater {
                        model: win.d.drives
                        delegate: BarRow {
                            required property var modelData
                            label: modelData.name
                            valueText: Theme.fmt(modelData.temp, 0, "°C")
                            colors: Theme.tempGradient(modelData.temp)
                            frac: modelData.temp != null ? (modelData.temp - 20) / ((modelData.max || 80) - 20) : 0
                        }
                    }
                }
            }
        }
    }
}
