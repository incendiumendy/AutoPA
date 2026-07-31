<template>
    <panel
        :icon="mdiChartTimelineVariant"
        title="AutoPA"
        :collapsible="true"
        card-class="autopa-panel"
        :loading="busy">
        <template #buttons>
            <select
                v-model="viewMode"
                class="autopa-view-select"
                :aria-label="labels.viewModeAria"
                @click.stop>
                <option value="auto">{{ labels.viewAuto }}</option>
                <option value="print">{{ labels.viewPrint }}</option>
                <option value="test">{{ labels.viewTest }}</option>
            </select>
            <v-btn icon tile :aria-label="labels.open" @click="openDashboard">
                <v-icon>{{ mdiOpenInNew }}</v-icon>
            </v-btn>
        </template>

        <v-card-text class="autopa-body py-2">
            <div class="d-flex align-center mb-2">
                <span class="autopa-live-dot mr-2" :class="{ live: isLive }" />
                <strong>{{ statusLabel }}</strong>
                <v-spacer />
                <v-chip x-small outlined :color="modeColor">{{ modeLabel }}</v-chip>
            </div>

            <v-alert v-if="error" dense text type="warning" class="mb-2">
                {{ labels.unavailable }}
            </v-alert>

            <div v-if="status && effectiveView === 'test'" class="autopa-sweeps mt-2">
                <div class="autopa-sweeps-head">
                    <span class="autopa-sweeps-title">{{ sweepsTitleText }}</span>
                    <v-spacer />
                    <span
                        class="autopa-sweeps-state"
                        :class="sweepReady ? 'ready' : 'locked'">
                        {{ sweepReady ? labels.sweepReady : labels.sweepLockedShort }}
                    </span>
                </div>
                <div class="autopa-sweeps-types">
                    <button
                        type="button"
                        class="autopa-sweep-type"
                        :class="{ active: sweepKind === 'pa' }"
                        @click="setSweepKind('pa')">
                        <v-icon x-small class="mr-1">{{ mdiSpeedometer }}</v-icon>
                        {{ labels.sweepPa }}
                    </button>
                    <button
                        type="button"
                        class="autopa-sweep-type"
                        :class="{ active: sweepKind === 'retract' }"
                        @click="setSweepKind('retract')">
                        <v-icon x-small class="mr-1">{{ mdiSwapVertical }}</v-icon>
                        {{ labels.sweepRetract }}
                    </button>
                </div>
                <div class="autopa-sweeps-params">
                    <label>
                        <span>{{ labels.sweepFrom }} <em>{{ sweepUnit }}</em></span>
                        <input
                            v-model="sweepParams.from"
                            type="number"
                            step="any"
                            inputmode="decimal" />
                    </label>
                    <label>
                        <span>{{ labels.sweepTo }} <em>{{ sweepUnit }}</em></span>
                        <input
                            v-model="sweepParams.to"
                            type="number"
                            step="any"
                            inputmode="decimal" />
                    </label>
                    <label>
                        <span>{{ labels.sweepStep }} <em>{{ sweepUnit }}</em></span>
                        <input
                            v-model="sweepParams.step"
                            type="number"
                            step="any"
                            inputmode="decimal" />
                    </label>
                    <label>
                        <span>{{ labels.sweepCycles }}</span>
                        <input
                            v-model="sweepParams.cycles"
                            type="number"
                            step="1"
                            inputmode="numeric" />
                    </label>
                    <label>
                        <span>{{ labels.sweepTargetZ }} <em>mm</em></span>
                        <input
                            v-model="sweepTargetZ"
                            type="number"
                            min="10"
                            max="300"
                            step="any"
                            inputmode="decimal" />
                    </label>
                    <label>
                        <span>{{ labels.sweepPrime }} <em>mm E</em></span>
                        <input
                            v-model="sweepPrimeE"
                            type="number"
                            min="0"
                            max="20"
                            step="any"
                            inputmode="decimal" />
                    </label>
                    <label v-if="sweepAutoApply">
                        <span>{{ labels.sweepApplyBound }} <em>±{{ sweepUnit }}</em></span>
                        <input
                            v-model="sweepApplyBound"
                            type="number"
                            step="any"
                            inputmode="decimal" />
                    </label>
                </div>
                <div class="autopa-sweeps-autoapply">
                    <label>
                        <input v-model="sweepAutoApply" type="checkbox" />
                        <span>{{ labels.sweepAutoApply }}</span>
                    </label>
                </div>
                <div class="autopa-sweeps-arm">
                    <input
                        v-model="sweepPhrase"
                        type="text"
                        class="autopa-phrase"
                        :placeholder="armPhrase"
                        :aria-label="labels.sweepPhraseAria"
                        autocomplete="off"
                        spellcheck="false" />
                    <button
                        type="button"
                        class="autopa-send"
                        :disabled="sweepSendDisabled"
                        @click="sendSweep">
                        {{ labels.sweepSend }}
                    </button>
                </div>
                <p v-if="sweepLockReason" class="autopa-sweep-note locked">
                    {{ sweepLockReason }}
                </p>
                <p v-else class="autopa-sweep-note">{{ sweepRestoreLabel }}</p>
                <p v-if="sweepMessage" class="autopa-sweep-note ok">{{ sweepMessage }}</p>
                <p v-if="sweepError" class="autopa-sweep-note error">{{ sweepError }}</p>
                <p v-if="sweepLastRunLabel" class="autopa-sweep-note dim">
                    {{ sweepLastRunLabel }}
                </p>
                <p
                    v-if="sweepApplyLabel"
                    class="autopa-sweep-note"
                    :class="sweepApplyApplied ? 'ok' : 'dim'">
                    {{ sweepApplyLabel }}
                </p>
            </div>

            <div v-if="status" class="autopa-sensors">
                <div class="autopa-sensor temperature">
                    <span>{{ labels.temperature }}</span>
                    <strong>{{ temperatureLabel }}</strong>
                    <small>{{ targetTemperatureLabel }}</small>
                </div>
                <div class="autopa-sensor motion">
                    <span>{{ labels.motion }}</span>
                    <strong>{{ motionLabel }}</strong>
                    <small>{{ motionAxesLabel }}</small>
                </div>
                <div class="autopa-sensor pressure">
                    <span>{{ labels.pressure }}</span>
                    <div class="autopa-barline">
                        <div class="autopa-vbar" aria-hidden="true">
                            <i class="autopa-vbar-fill" :style="pressureBarStyle"></i>
                            <b class="autopa-vbar-zero"></b>
                        </div>
                        <div class="autopa-vbar-value">
                            <strong>{{ pressureLabel }}</strong>
                            <small>{{ pressureDirectionLabel }}</small>
                        </div>
                    </div>
                </div>
            </div>

            <div v-if="status" class="autopa-context-line mt-2">
                <span><b>PA</b> {{ number(status.printer.pressureAdvance, 3) }}</span>
                <span><b>{{ labels.layer }}</b> {{ contextLayer }}</span>
                <span><b>{{ labels.feature }}</b> {{ featureLabel }}</span>
                <span><b>{{ labels.speedShort }}</b> {{ speedLabel }}</span>
                <span><b>{{ labels.flowShort }}</b> {{ flowLabel }}</span>
            </div>

            <div class="autopa-window mt-2" :class="{ eligible: paWindowActive }">
                <span>{{ contextStateLabel }}</span>
                <span class="autopa-quality">{{ qualityLabel }}</span>
            </div>

            <div class="autopa-actions mt-2">
                <v-btn
                    x-small
                    outlined
                    :color="liveCaptureActive ? 'success' : 'primary'"
                    :disabled="liveToggleDisabled"
                    @click="toggleLiveData">
                    {{ liveCaptureActive ? labels.liveOff : labels.liveOn }}
                </v-btn>
                <v-btn
                    x-small
                    outlined
                    color="warning"
                    :disabled="busy || !status || applyActive"
                    @click="toggleDryRun">
                    {{ dryRunActive ? labels.disable : labels.enable }}
                </v-btn>
                <v-spacer />
                <v-btn x-small text color="primary" @click="openDashboard">
                    {{ labels.open }}
                </v-btn>
            </div>

            <p v-if="actionError" class="caption error--text mt-1 mb-0">
                {{ actionError }}
            </p>
            <p v-if="applyActive" class="caption warning--text mt-1 mb-0">
                {{ labels.applyNotice }}
            </p>
        </v-card-text>
    </panel>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import { mdiChartTimelineVariant, mdiOpenInNew, mdiSpeedometer, mdiSwapVertical } from '@mdi/js'
import BaseMixin from '@/components/mixins/base'
import Panel from '@/components/ui/Panel.vue'

type AutoPaMode = 'off' | 'dry_run' | 'apply'
const PRESSURE_DISPLAY_DEADBAND = 0.1
const PRESSURE_SMOOTHING_ALPHA = 0.25
const MOTION_DISPLAY_DEADBAND_MM_S2 = 200

interface AutoPaContext {
    active: boolean
    layer: number | null
    z_mm: number | null
    feature: string
    object: string | null
    pa_eligible: boolean
    eligibility_reason: string
}

interface SweepParams {
    from: string
    to: string
    step: string
    cycles: string
}

interface SweepRunInfo {
    startedAt: string
    cycles: number
    scriptLines: number
    retractValues?: number[]
    restoreRetractMm?: number
    kValues?: number[]
    restoreAdvance?: number
    autoApply?: boolean
    applyBoundMm?: number
    applyBound?: number
}

interface SweepApplyInfo {
    applied: boolean
    runtimeOnly?: boolean
    reason?: string | null
    previousMm?: number
    appliedMm?: number
    previous?: number
    appliedValue?: number
    deviationMm?: number
    deviation?: number
    boundMm?: number
    bound?: number
    source?: string | null
    at?: string
    printerAction?: string
}

interface SweepStatusInfo {
    allowPrinterCommands: boolean
    lastRun: SweepRunInfo | null
    lastError: string | null
    lastApply: SweepApplyInfo | null
}

interface AutoPaStatus {
    printer: {
        connected: boolean
        temperature: number | null
        target: number | null
        pressureAdvance: number | null
        printState: string | null
        retractLength: number | null
    }
    capture: {
        state: string
        ageSeconds: number | null
        manager?: {
            active: boolean
            canStart: boolean
            canStop: boolean
        }
    }
    sensors: {
        alps: {
            state: string
            normalized: number | null
        }
        accelerometer: {
            enabled: boolean
            state: string
            motionX: number | null
            motionY: number | null
            motionZ: number | null
            rmsX: number | null
            rmsY: number | null
            rmsZ: number | null
        }
    }
    quality: {
        state: string
        message: string
    }
    control: {
        mode: AutoPaMode
        adaptivePAEnabled: boolean
        paContextEligible: boolean
        toolheadVelocityMmS: number | null
        volumetricFlowMm3S: number | null
        gcodeContext: AutoPaContext | null
    }
}

@Component({
    components: { Panel },
})
export default class AutopaPanel extends Mixins(BaseMixin) {
    mdiChartTimelineVariant = mdiChartTimelineVariant
    mdiOpenInNew = mdiOpenInNew
    mdiSpeedometer = mdiSpeedometer
    mdiSwapVertical = mdiSwapVertical

    status: AutoPaStatus | null = null
    error = ''
    actionError = ''
    busy = false
    timer: number | null = null
    sweepKind: 'retract' | 'pa' = 'pa'
    retractParams: SweepParams = { from: '0.2', to: '1.4', step: '0.2', cycles: '5' }
    paParams: SweepParams = { from: '0', to: '0.08', step: '0.01', cycles: '6' }
    sweepTargetZ = '50'
    sweepPrimeE = '5'
    sweepAutoApply = true
    retractApplyBound = '1.5'
    paApplyBound = '0.09'
    sweepPhrase = ''
    sweepBusy = false
    sweepMessage = ''
    sweepError = ''
    retractSweep: SweepStatusInfo | null = null
    paSweep: SweepStatusInfo | null = null
    readonly armPhrase = 'AUTOPA VALIDIEREN'
    pressureHistory: number[] = []
    readonly pressureHistoryLimit = 90
    pressureSmoothed: number | null = null
    viewMode: 'auto' | 'print' | 'test' = 'auto'
    mounted() {
        void this.refresh()
        this.timer = window.setInterval(() => void this.refresh(), 1000)
    }

    beforeDestroy() {
        if (this.timer !== null) window.clearInterval(this.timer)
    }

    get isGerman() {
        return this.$i18n.locale.toLowerCase().startsWith('de')
    }

    get labels() {
        return this.isGerman
            ? {
                  unavailable: 'AutoPA ist nicht erreichbar. Der Druck läuft unverändert weiter.',
                  pressure: 'Düsendruck',
                  temperature: 'Temperatur',
                  motion: 'Bewegung',
                  layer: 'Layer',
                  feature: 'Feature',
                  speedShort: 'v',
                  flowShort: 'Flow',
                  enable: 'Dry-Run ein',
                  disable: 'Ausschalten',
                  liveOn: 'Live ein',
                  liveOff: 'Live aus',
                  open: 'AutoPA öffnen',
                  waiting: 'Wartet auf Live-Daten',
                  live: 'Live-Daten aktiv',
                  applyNotice: 'Bewaffneter Modus kann nur in AutoPA beendet werden.',
                  windowActive: 'PA-Messfenster aktiv',
                  windowIgnored: 'PA-Messfenster ignoriert',
                  contextMissing: 'Kein ausgeführter G-Code-Kontext',
                  sweepsTitleRetract: 'Rückzug-Kalibrierung',
                  sweepsTitlePa: 'PA-Kalibrierung',
                  sweepRetract: 'Rückzug',
                  sweepPa: 'PA (K)',
                  sweepFrom: 'Von',
                  sweepTo: 'Bis',
                  sweepStep: 'Schritt',
                  sweepCycles: 'Zyklen',
                  sweepSend: 'Senden',
                  sweepReady: 'Bereit',
                  sweepLockedShort: 'Gesperrt',
                  sweepLockedServer: 'Server-seitig gesperrt.',
                  sweepRestore: 'Restore am Ende',
                  sweepPhraseAria: 'Bestätigung für den Sweep',
                  sweepSent: 'Sweep an den Drucker gesendet.',
                  sweepInvalid: 'Bitte gültige Zahlen eingeben.',
                  sweepLastRun: 'Letzter Lauf',
                  sweepTargetZ: 'Ziel-Z',
                  sweepPrime: 'Prime',
                  sweepAutoApply: 'Auto-Übernahme',
                  sweepApplyBound: 'Grenze',
                  sweepApplyNoRecommendation: 'Keine eindeutige Empfehlung — nichts übernommen.',
                  sweepApplyNoDataset: 'Kein Messdatensatz — keine Auswertung möglich.',
                  sweepApplyAnalysisFailed: 'Auswertung fehlgeschlagen — nichts übernommen.',
                  sweepApplyValuesUnavailable: 'Aktueller Wert nicht lesbar — nichts übernommen.',
                  viewModeAria: 'Ansicht',
                  viewAuto: 'Auto',
                  viewPrint: 'Druck',
                  viewTest: 'Test',
              }
            : {
                  unavailable: 'AutoPA is unavailable. Printing continues unchanged.',
                  pressure: 'Nozzle load',
                  temperature: 'Temperature',
                  motion: 'Motion',
                  layer: 'Layer',
                  feature: 'Feature',
                  speedShort: 'v',
                  flowShort: 'Flow',
                  enable: 'Enable dry-run',
                  disable: 'Turn off',
                  liveOn: 'Live on',
                  liveOff: 'Live off',
                  open: 'Open AutoPA',
                  waiting: 'Waiting for live data',
                  live: 'Live data active',
                  applyNotice: 'Armed mode can only be stopped in AutoPA.',
                  windowActive: 'PA evidence window active',
                  windowIgnored: 'PA evidence window ignored',
                  contextMissing: 'No executed G-code context',
                  sweepsTitleRetract: 'Retraction calibration',
                  sweepsTitlePa: 'PA calibration',
                  sweepRetract: 'Retract',
                  sweepPa: 'PA (K)',
                  sweepFrom: 'From',
                  sweepTo: 'To',
                  sweepStep: 'Step',
                  sweepCycles: 'Cycles',
                  sweepSend: 'Send',
                  sweepReady: 'Ready',
                  sweepLockedShort: 'Locked',
                  sweepLockedServer: 'Locked server-side.',
                  sweepRestore: 'Restore at the end',
                  sweepPhraseAria: 'Sweep confirmation',
                  sweepSent: 'Sweep sent to the printer.',
                  sweepInvalid: 'Please enter valid numbers.',
                  sweepLastRun: 'Last run',
                  sweepTargetZ: 'Target Z',
                  sweepPrime: 'Prime',
                  sweepAutoApply: 'Auto-apply',
                  sweepApplyBound: 'Limit',
                  sweepApplyNoRecommendation: 'No conclusive recommendation — nothing applied.',
                  sweepApplyNoDataset: 'No capture dataset — analysis not possible.',
                  sweepApplyAnalysisFailed: 'Analysis failed — nothing applied.',
                  sweepApplyValuesUnavailable: 'Current value unreadable — nothing applied.',
                  viewModeAria: 'View',
                  viewAuto: 'Auto',
                  viewPrint: 'Print',
                  viewTest: 'Test',
              }
    }

    get isLive() {
        return (
            !this.error &&
            this.status?.capture.state === 'ok' &&
            this.status?.sensors.alps.state === 'ok'
        )
    }

    get statusLabel() {
        return this.isLive ? this.labels.live : this.labels.waiting
    }

    get mode() {
        return this.status?.control.mode ?? 'off'
    }

    get dryRunActive() {
        return this.mode === 'dry_run'
    }

    get applyActive() {
        return this.mode === 'apply'
    }

    get modeLabel() {
        if (this.applyActive) return this.isGerman ? 'BEWAFFNET' : 'ARMED'
        if (this.dryRunActive) return 'DRY-RUN'
        return this.isGerman ? 'AUS' : 'OFF'
    }

    get modeColor() {
        if (this.applyActive) return 'error'
        if (this.dryRunActive) return 'warning'
        return 'grey'
    }

    get pressureValue() {
        if (!this.isLive) return null
        return this.pressureSmoothed
    }

    get pressureLabel() {
        const value = this.pressureValue
        if (value === null || value === undefined) return '—'
        if (Math.abs(value) < PRESSURE_DISPLAY_DEADBAND) return '≈ 0 %'
        const sign = value > 0 ? '+' : '−'
        return `${sign}${Math.abs(value * 100).toFixed(1)} %`
    }

    get pressureDirectionLabel() {
        const value = this.pressureValue
        if (
            value === null ||
            value === undefined ||
            Math.abs(value) < PRESSURE_DISPLAY_DEADBAND
        ) {
            return this.isGerman ? 'Nullpunkt' : 'Baseline'
        }
        if (value > 0) return this.isGerman ? '+ Druck' : '+ Load'
        return this.isGerman ? '− Zug' : '− Tension'
    }

    get pressureBarScale() {
        const peak = this.pressureHistory.reduce(
            (max, value) => Math.max(max, Math.abs(value)), 0)
        return Math.max(0.3, peak * 1.15)
    }

    get pressureBarStyle() {
        const value = this.pressureValue
        if (
            value === null ||
            value === undefined ||
            Math.abs(value) < PRESSURE_DISPLAY_DEADBAND
        ) {
            return { display: 'none' }
        }
        const fraction = Math.min(1, Math.abs(value) / this.pressureBarScale)
        const height = Math.max(3, fraction * 50)
        return value >= 0
            ? { bottom: '50%', height: `${height}%` }
            : { top: '50%', height: `${height}%` }
    }

    get temperatureLabel() {
        const value = this.status?.printer.temperature
        return value === null || value === undefined ? '—' : `${this.number(value, 1)} °C`
    }

    get targetTemperatureLabel() {
        const value = this.status?.printer.target
        if (value === null || value === undefined || value <= 0) {
            return this.isGerman ? 'Heizung aus' : 'Heater off'
        }
        return `${this.isGerman ? 'Ziel' : 'Target'} ${this.number(value, 0)} °C`
    }

    get motionRms() {
        const sensor = this.status?.sensors.accelerometer
        if (!sensor?.enabled) return null
        const values = [sensor.rmsX, sensor.rmsY, sensor.rmsZ]
        if (values.some((value) => value === null || value === undefined)) return null
        return Math.sqrt(values.reduce((sum, value) => sum + Number(value) ** 2, 0))
    }

    get motionLabel() {
        const value = this.motionRms
        if (value === null) return '—'
        if (value < MOTION_DISPLAY_DEADBAND_MM_S2) return '≈ 0 m/s²'
        return `${this.number(value / 1000, 2)} m/s²`
    }

    get motionAxesLabel() {
        const sensor = this.status?.sensors.accelerometer
        if (!sensor?.enabled) return this.isGerman ? 'deaktiviert' : 'disabled'
        const axis = (value: number | null) => {
            if (value === null || value === undefined) return '—'
            if (Math.abs(value) < MOTION_DISPLAY_DEADBAND_MM_S2) return '0'
            return this.number(value / 1000, 1)
        }
        return `X ${axis(sensor.motionX)} · Y ${axis(sensor.motionY)} · Z ${axis(sensor.motionZ)}`
    }

    get context() {
        return this.status?.control.gcodeContext ?? null
    }

    get contextLayer() {
        if (!this.context?.active || this.context.layer === null) return '—'
        const z = this.context.z_mm === null ? '' : ` · Z ${this.number(this.context.z_mm, 2)}`
        return `${this.context.layer}${z}`
    }

    get featureLabel() {
        if (!this.context?.active) return '—'
        const labels: Record<string, string> = this.isGerman
            ? {
                  external_perimeter: 'Außenwand',
                  internal_perimeter: 'Innenwand',
                  infill: 'Infill',
                  solid_infill: 'Massives Infill',
                  gap_fill: 'Lückenfüllung',
                  bridge: 'Brücke',
                  support: 'Support',
                  skirt_brim: 'Skirt / Brim',
                  ironing: 'Glätten',
                  unknown: 'Unbekannt',
              }
            : {
                  external_perimeter: 'Outer wall',
                  internal_perimeter: 'Inner wall',
                  infill: 'Infill',
                  solid_infill: 'Solid infill',
                  gap_fill: 'Gap fill',
                  bridge: 'Bridge',
                  support: 'Support',
                  skirt_brim: 'Skirt / brim',
                  ironing: 'Ironing',
                  unknown: 'Unknown',
              }
        return labels[this.context.feature] ?? this.context.feature
    }

    get speedLabel() {
        const value = this.status?.control.toolheadVelocityMmS
        return value === null || value === undefined ? '—' : `${this.number(value, 1)} mm/s`
    }

    get flowLabel() {
        const value = this.status?.control.volumetricFlowMm3S
        return value === null || value === undefined ? '—' : `${this.number(value, 1)} mm³/s`
    }

    get paWindowActive() {
        return this.status?.control.paContextEligible === true
    }

    get contextStateLabel() {
        if (!this.context?.active) return this.labels.contextMissing
        return this.paWindowActive ? this.labels.windowActive : this.labels.windowIgnored
    }

    get qualityLabel() {
        const state = this.status?.quality.state
        if (state === 'ok') return 'OK'
        if (state === 'error') return this.isGerman ? 'Fehler' : 'Error'
        if (state === 'warning') return this.isGerman ? 'Prüfen' : 'Check'
        return this.isGerman ? 'Wartet' : 'Waiting'
    }

    get effectiveView() {
        if (this.viewMode !== 'auto') return this.viewMode
        return this.printState === 'standby' ? 'test' : 'print'
    }

    get sweepsTitleText() {
        return this.sweepKind === 'retract'
            ? this.labels.sweepsTitleRetract
            : this.labels.sweepsTitlePa
    }

    get liveCaptureActive() {
        return this.status?.capture.manager?.active === true
    }

    get sweepParams(): SweepParams {
        return this.sweepKind === 'retract' ? this.retractParams : this.paParams
    }

    get activeSweep(): SweepStatusInfo | null {
        return this.sweepKind === 'retract' ? this.retractSweep : this.paSweep
    }

    get sweepUnit() {
        return this.sweepKind === 'retract' ? 'mm' : 'K'
    }

    get sweepApplyBound(): string {
        return this.sweepKind === 'retract' ? this.retractApplyBound : this.paApplyBound
    }

    set sweepApplyBound(value: string) {
        if (this.sweepKind === 'retract') this.retractApplyBound = value
        else this.paApplyBound = value
    }

    get sweepApplyDigits() {
        return this.sweepKind === 'retract' ? 2 : 3
    }

    get sweepApplyInfo(): SweepApplyInfo | null {
        return this.activeSweep?.lastApply ?? null
    }

    get sweepApplyApplied() {
        return this.sweepApplyInfo?.applied === true
    }

    get sweepApplyLabel() {
        const apply = this.sweepApplyInfo
        if (!apply) return ''
        const digits = this.sweepApplyDigits
        const isRetract = this.sweepKind === 'retract'
        if (apply.applied) {
            const previous = isRetract ? apply.previousMm : apply.previous
            const applied = isRetract ? apply.appliedMm : apply.appliedValue
            return this.isGerman
                ? `Übernommen (Laufzeit): ${this.number(previous, digits)} → ${this.number(applied, digits)} ${this.sweepUnit}`
                : `Applied (runtime): ${this.number(previous, digits)} → ${this.number(applied, digits)} ${this.sweepUnit}`
        }
        if (apply.reason === 'outside_bounds') {
            const deviation = isRetract ? apply.deviationMm : apply.deviation
            const bound = isRetract ? apply.boundMm : apply.bound
            return this.isGerman
                ? `Nicht übernommen: Abweichung ${this.number(deviation, digits)} > Grenze ${this.number(bound, digits)} ${this.sweepUnit}`
                : `Not applied: deviation ${this.number(deviation, digits)} > limit ${this.number(bound, digits)} ${this.sweepUnit}`
        }
        if (apply.reason === 'no_recommendation') return this.labels.sweepApplyNoRecommendation
        if (apply.reason === 'no_capture_dataset') return this.labels.sweepApplyNoDataset
        if (apply.reason === 'values_unavailable') return this.labels.sweepApplyValuesUnavailable
        return this.labels.sweepApplyAnalysisFailed
    }

    get printState() {
        return this.status?.printer.printState ?? null
    }

    get sweepReady() {
        return (
            this.activeSweep?.allowPrinterCommands === true &&
            this.printState === 'standby'
        )
    }

    get sweepLockReason() {
        if (!this.activeSweep) return ''
        if (!this.activeSweep.allowPrinterCommands) return this.labels.sweepLockedServer
        if (this.printState !== 'standby') {
            const state = this.printState ?? (this.isGerman ? 'unbekannt' : 'unknown')
            return this.isGerman
                ? `Gesperrt: Drucker ist „${state}“ — Sweep nur im Standby.`
                : `Locked: printer is "${state}" — sweep requires standby.`
        }
        return ''
    }

    get sweepRestoreLabel() {
        if (this.sweepKind === 'retract') {
            const value = this.status?.printer.retractLength
            return `${this.labels.sweepRestore}: ${this.number(value, 2)} mm`
        }
        const value = this.status?.printer.pressureAdvance
        return `${this.labels.sweepRestore}: ${this.number(value, 3)}`
    }

    get sweepSendDisabled() {
        return (
            this.sweepBusy ||
            !this.status ||
            !this.sweepReady ||
            this.sweepPhrase !== this.armPhrase
        )
    }

    get sweepLastRunLabel() {
        const run = this.activeSweep?.lastRun
        if (!run) return ''
        const values = run.retractValues ?? run.kValues ?? []
        const range = values.length
            ? `${values[0]}–${values[values.length - 1]} ${this.sweepUnit}`
            : '—'
        const restore =
            run.restoreRetractMm !== undefined
                ? `${this.number(run.restoreRetractMm, 2)} mm`
                : this.number(run.restoreAdvance, 3)
        return `${this.labels.sweepLastRun}: ${range} à ${run.cycles} · Restore ${restore}`
    }

    get liveToggleDisabled() {
        if (this.busy || !this.status) return true
        const manager = this.status.capture.manager
        if (!manager) return true
        return this.liveCaptureActive ? !manager.canStop : !manager.canStart
    }

    number(value: number | null | undefined, digits: number) {
        return value === null || value === undefined || !Number.isFinite(value) ? '—' : value.toFixed(digits)
    }

    async refresh() {
        await Promise.all([this.refreshAutoPa(), this.refreshSweeps()])
    }

    async refreshAutoPa() {
        try {
            const response = await fetch('/autopa/api/status', {
                cache: 'no-store',
                headers: { Accept: 'application/json' },
            })
            if (!response.ok) throw new Error(`HTTP ${response.status}`)
            this.status = (await response.json()) as AutoPaStatus
            this.error = ''
            const pressure = this.status.sensors?.alps?.normalized
            const live =
                this.status.capture?.state === 'ok' &&
                this.status.sensors?.alps?.state === 'ok'
            if (live && typeof pressure === 'number' && Number.isFinite(pressure)) {
                this.pressureSmoothed =
                    this.pressureSmoothed === null
                        ? pressure
                        : this.pressureSmoothed +
                          PRESSURE_SMOOTHING_ALPHA * (pressure - this.pressureSmoothed)
                this.pressureHistory.push(this.pressureSmoothed)
                if (this.pressureHistory.length > this.pressureHistoryLimit) {
                    this.pressureHistory.shift()
                }
            } else {
                this.pressureSmoothed = null
                this.pressureHistory = []
            }
        } catch (error) {
            this.error = error instanceof Error ? error.message : String(error)
        }
    }

    async toggleDryRun() {
        if (!this.status || this.applyActive) return
        this.busy = true
        this.actionError = ''
        try {
            const payload = this.dryRunActive
                ? { mode: 'off' }
                : { mode: 'dry_run', adaptive_pa_enabled: true }
            const response = await fetch('/autopa/api/control/config', {
                method: 'POST',
                cache: 'no-store',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            })
            if (!response.ok) throw new Error(`HTTP ${response.status}`)
            await this.refresh()
        } catch (error) {
            this.error = error instanceof Error ? error.message : String(error)
        } finally {
            this.busy = false
        }
    }

    async toggleLiveData() {
        if (this.liveToggleDisabled) return
        this.busy = true
        this.actionError = ''
        try {
            const action = this.liveCaptureActive ? 'stop' : 'start'
            const response = await fetch(`/autopa/api/capture/${action}`, {
                method: 'POST',
                cache: 'no-store',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: '{}',
            })
            if (!response.ok) {
                const payload = (await response.json().catch(() => ({}))) as {
                    error?: string
                }
                throw new Error(payload.error ?? `HTTP ${response.status}`)
            }
            await this.refresh()
        } catch (error) {
            this.actionError = error instanceof Error ? error.message : String(error)
        } finally {
            this.busy = false
        }
    }

    openDashboard() {
        window.location.assign('/autopa/')
    }

    setSweepKind(kind: 'retract' | 'pa') {
        if (this.sweepKind === kind) return
        this.sweepKind = kind
        this.sweepMessage = ''
        this.sweepError = ''
    }

    async refreshSweeps() {
        try {
            const [retractResponse, paResponse] = await Promise.all([
                fetch('/autopa/api/sweep', {
                    cache: 'no-store',
                    headers: { Accept: 'application/json' },
                }),
                fetch('/autopa/api/pa-sweep', {
                    cache: 'no-store',
                    headers: { Accept: 'application/json' },
                }),
            ])
            if (retractResponse.ok) {
                this.retractSweep = (await retractResponse.json()) as SweepStatusInfo
            }
            if (paResponse.ok) {
                this.paSweep = (await paResponse.json()) as SweepStatusInfo
            }
        } catch (error) {
            // Sweep-Status ist optional; der Rest der Kachel bleibt nutzbar.
        }
    }

    async sendSweep() {
        if (this.sweepSendDisabled) return
        this.sweepBusy = true
        this.sweepMessage = ''
        this.sweepError = ''
        try {
            const params = this.sweepParams
            const values = [params.from, params.to, params.step, params.cycles].map(
                (raw) => Number(String(raw).replace(',', '.'))
            )
            if (values.some((value) => !Number.isFinite(value))) {
                throw new Error(this.labels.sweepInvalid)
            }
            const extras: Record<string, number> = {}
            const optionalFields: [string, string][] = [
                ['start_z', this.sweepTargetZ],
                ['prime_e', this.sweepPrimeE],
            ]
            if (this.sweepAutoApply) {
                optionalFields.push(['apply_bound', this.sweepApplyBound])
            }
            for (const [key, raw] of optionalFields) {
                const trimmed = String(raw).trim()
                if (trimmed === '') continue
                const parsed = Number(trimmed.replace(',', '.'))
                if (!Number.isFinite(parsed)) {
                    throw new Error(this.labels.sweepInvalid)
                }
                extras[key] = parsed
            }
            const payload =
                this.sweepKind === 'retract'
                    ? {
                          phrase: this.sweepPhrase,
                          r_start: values[0],
                          r_stop: values[1],
                          r_step: values[2],
                          cycles: values[3],
                          auto_apply: this.sweepAutoApply,
                          ...extras,
                      }
                    : {
                          phrase: this.sweepPhrase,
                          k_start: values[0],
                          k_stop: values[1],
                          k_step: values[2],
                          cycles: values[3],
                          auto_apply: this.sweepAutoApply,
                          ...extras,
                      }
            const url =
                this.sweepKind === 'retract'
                    ? '/autopa/api/sweep/run'
                    : '/autopa/api/pa-sweep/run'
            const response = await fetch(url, {
                method: 'POST',
                cache: 'no-store',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            })
            if (!response.ok) {
                const body = (await response.json().catch(() => ({}))) as {
                    error?: string
                }
                throw new Error(body.error ?? `HTTP ${response.status}`)
            }
            this.sweepMessage = this.labels.sweepSent
            this.sweepPhrase = ''
            await this.refreshSweeps()
        } catch (error) {
            this.sweepError = error instanceof Error ? error.message : String(error)
        } finally {
            this.sweepBusy = false
        }
    }

}
</script>

<style scoped>
.autopa-live-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--v-warning-base);
    box-shadow: 0 0 0 3px rgba(255, 152, 0, 0.12);
}

.autopa-live-dot.live {
    background: var(--v-success-base);
    box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.14);
}

.autopa-body {
    font-size: 0.8rem;
}

.autopa-sensors {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 5px;
}

.autopa-sensor {
    min-width: 0;
    padding: 6px 7px;
    border: 1px solid rgba(128, 128, 128, 0.2);
    border-radius: 4px;
}

.autopa-sensor span,
.autopa-sensor strong,
.autopa-sensor small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.autopa-sensor span {
    color: var(--v-secondary-lighten2);
    font-size: 0.65rem;
}

.autopa-sensor strong {
    margin-top: 1px;
    font-size: 0.83rem;
}

.autopa-sensor small {
    margin-top: 1px;
    color: var(--v-secondary-lighten1);
    font-size: 0.62rem;
}

.autopa-sensor.motion strong {
    color: var(--v-success-base);
}

.autopa-sensor.pressure strong {
    color: var(--v-primary-base);
}

.autopa-context-line {
    display: flex;
    align-items: center;
    gap: 4px 10px;
    overflow: hidden;
    color: var(--v-secondary-lighten1);
    font-size: 0.67rem;
    white-space: nowrap;
}

.autopa-context-line span {
    overflow: hidden;
    text-overflow: ellipsis;
}

.autopa-context-line b {
    color: var(--v-secondary-lighten2);
    font-weight: 500;
}

.autopa-window {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 7px 9px;
    border-left: 3px solid var(--v-warning-base);
    border-radius: 3px;
    background: rgba(255, 152, 0, 0.07);
    color: var(--v-warning-base);
    font-size: 0.78rem;
}

.autopa-quality {
    flex: 0 0 auto;
    font-weight: 700;
}

.autopa-window.eligible {
    border-left-color: var(--v-success-base);
    background: rgba(76, 175, 80, 0.07);
    color: var(--v-success-base);
}

.autopa-actions {
    display: flex;
    align-items: center;
    gap: 5px;
}

.autopa-sweeps {
    padding: 7px 8px 8px;
    border: 1px solid rgba(128, 128, 128, 0.2);
    border-radius: 4px;
}

.autopa-sweeps-head {
    display: flex;
    align-items: center;
}

.autopa-sweeps-title {
    color: var(--v-secondary-lighten2);
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.autopa-sweeps-state {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.autopa-sweeps-state.ready {
    color: var(--v-success-base);
}

.autopa-sweeps-state.locked {
    color: var(--v-warning-base);
}

.autopa-sweeps-types {
    display: flex;
    gap: 5px;
    margin-top: 6px;
}

.autopa-sweep-type {
    flex: 1;
    padding: 3px 0;
    border: 1px solid rgba(128, 128, 128, 0.25);
    border-radius: 4px;
    background: transparent;
    color: var(--v-secondary-lighten1);
    font-size: 0.7rem;
    cursor: pointer;
}

.autopa-sweep-type.active {
    border-color: var(--v-primary-base);
    background: rgba(30, 136, 229, 0.1);
    color: var(--v-primary-base);
    font-weight: 600;
}

.autopa-sweeps-params {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 5px;
    margin-top: 6px;
}

.autopa-sweeps-params label {
    min-width: 0;
}

.autopa-sweeps-params label > span {
    display: flex;
    justify-content: space-between;
    color: var(--v-secondary-lighten2);
    font-size: 0.58rem;
}

.autopa-sweeps-params em {
    font-style: normal;
}

.autopa-sweeps-params input {
    width: 100%;
    margin-top: 2px;
    padding: 2px 5px;
    border: 1px solid rgba(128, 128, 128, 0.25);
    border-radius: 3px;
    background: transparent;
    color: inherit;
    font-size: 0.72rem;
}

.autopa-sweeps-arm {
    display: flex;
    gap: 5px;
    margin-top: 6px;
}

.autopa-sweeps-autoapply {
    margin-top: 5px;
}

.autopa-sweeps-autoapply label {
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
    color: var(--v-secondary-lighten2);
    font-size: 0.62rem;
}

.autopa-sweeps-autoapply input[type='checkbox'] {
    width: 12px;
    height: 12px;
    margin: 0;
    accent-color: var(--v-primary-base);
}

.autopa-phrase {
    flex: 1;
    min-width: 0;
    padding: 3px 6px;
    border: 1px dashed rgba(128, 128, 128, 0.35);
    border-radius: 3px;
    background: transparent;
    color: inherit;
    font-size: 0.68rem;
    letter-spacing: 0.04em;
}

.autopa-send {
    flex: 0 0 auto;
    padding: 3px 12px;
    border: 0;
    border-radius: 3px;
    background: var(--v-primary-base);
    color: #fff;
    font-size: 0.7rem;
    font-weight: 600;
    cursor: pointer;
}

.autopa-send:disabled {
    opacity: 0.35;
    cursor: not-allowed;
}

.autopa-sweep-note {
    margin: 4px 0 0;
    color: var(--v-secondary-lighten1);
    font-size: 0.63rem;
    line-height: 1.35;
}

.autopa-sweep-note.locked {
    color: var(--v-warning-base);
}

.autopa-sweep-note.ok {
    color: var(--v-success-base);
}

.autopa-sweep-note.error {
    color: var(--v-error-base);
}

.autopa-sweep-note.dim {
    color: var(--v-secondary-lighten2);
}

.autopa-view-select {
    align-self: center;
    height: 22px;
    margin-right: 2px;
    padding: 0 4px;
    border: 1px solid rgba(128, 128, 128, 0.3);
    border-radius: 4px;
    background: transparent;
    color: var(--v-secondary-lighten1);
    font-size: 0.65rem;
}

.autopa-view-select option {
    color: #111;
}

.autopa-barline {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-top: 1px;
}

.autopa-vbar {
    position: relative;
    flex: 0 0 auto;
    width: 6px;
    height: 30px;
    border: 1px solid rgba(128, 128, 128, 0.25);
    border-radius: 3px;
}

.autopa-vbar-zero {
    position: absolute;
    left: 0;
    right: 0;
    top: 50%;
    height: 1px;
    background: rgba(128, 128, 128, 0.55);
}

.autopa-vbar-fill {
    position: absolute;
    left: 1px;
    right: 1px;
    border-radius: 2px;
    background: var(--v-primary-base);
    transition:
        top 320ms ease,
        bottom 320ms ease,
        height 320ms ease;
}

.autopa-vbar-value {
    min-width: 0;
}

.autopa-vbar-value strong,
.autopa-vbar-value small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
    .autopa-vbar-fill {
        transition: none;
    }
}

@media (max-width: 420px) {
    .autopa-sensors {
        grid-template-columns: 1fr;
    }

    .autopa-sweeps-params {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .autopa-sensor {
        display: grid;
        grid-template-columns: 0.9fr 1fr 1.3fr;
        align-items: center;
        gap: 6px;
    }

    .autopa-sensor.pressure {
        grid-template-columns: 0.9fr 2.3fr;
    }

    .autopa-sensor.pressure .autopa-barline {
        grid-column: 2;
    }

    .autopa-sensor strong,
    .autopa-sensor small {
        margin-top: 0;
    }
}
</style>
