<template>
    <panel
        :icon="mdiChartTimelineVariant"
        title="AutoPA"
        :collapsible="true"
        card-class="autopa-panel"
        :loading="busy">
        <template #buttons>
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
                    <strong>{{ pressureLabel }}</strong>
                    <small>{{ pressureDirectionLabel }}</small>
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

            <div
                v-if="localVisionInstalled"
                class="autopa-service-row mt-2"
                :class="{ healthy: localVisionHealthy, failed: !localVisionHealthy }">
                <span class="autopa-service-dot mr-2" />
                <strong>Local Vision</strong>
                <v-spacer />
                <span>{{ localVisionLabel }}</span>
                <v-btn
                    icon
                    x-small
                    class="ml-1"
                    :aria-label="labels.openLocalVision"
                    @click="openLocalVision">
                    <v-icon small>{{ mdiOpenInNew }}</v-icon>
                </v-btn>
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
import { mdiChartTimelineVariant, mdiOpenInNew } from '@mdi/js'
import BaseMixin from '@/components/mixins/base'
import Panel from '@/components/ui/Panel.vue'

type AutoPaMode = 'off' | 'dry_run' | 'apply'
const PRESSURE_DISPLAY_DEADBAND = 0.1
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

interface AutoPaStatus {
    printer: {
        connected: boolean
        temperature: number | null
        target: number | null
        pressureAdvance: number | null
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

type LocalVisionState = 'unknown' | 'absent' | 'ok' | 'error'

@Component({
    components: { Panel },
})
export default class AutopaPanel extends Mixins(BaseMixin) {
    mdiChartTimelineVariant = mdiChartTimelineVariant
    mdiOpenInNew = mdiOpenInNew

    status: AutoPaStatus | null = null
    error = ''
    actionError = ''
    busy = false
    timer: number | null = null
    localVisionState: LocalVisionState = 'unknown'

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
                  openLocalVision: 'Local Vision öffnen',
                  waiting: 'Wartet auf Live-Daten',
                  live: 'Live-Daten aktiv',
                  localVisionOk: 'OK',
                  localVisionError: 'Fehler',
                  applyNotice: 'Bewaffneter Modus kann nur in AutoPA beendet werden.',
                  windowActive: 'PA-Messfenster aktiv',
                  windowIgnored: 'PA-Messfenster ignoriert',
                  contextMissing: 'Kein ausgeführter G-Code-Kontext',
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
                  openLocalVision: 'Open Local Vision',
                  waiting: 'Waiting for live data',
                  live: 'Live data active',
                  localVisionOk: 'OK',
                  localVisionError: 'Error',
                  applyNotice: 'Armed mode can only be stopped in AutoPA.',
                  windowActive: 'PA evidence window active',
                  windowIgnored: 'PA evidence window ignored',
                  contextMissing: 'No executed G-code context',
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

    get pressureLabel() {
        const value = this.status?.sensors.alps.normalized
        if (value === null || value === undefined) return '—'
        if (Math.abs(value) < PRESSURE_DISPLAY_DEADBAND) return '≈ 0 %'
        const sign = value > 0 ? '+' : '−'
        return `${sign}${Math.abs(value * 100).toFixed(1)} %`
    }

    get pressureDirectionLabel() {
        const value = this.status?.sensors.alps.normalized
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

    get liveCaptureActive() {
        return this.status?.capture.manager?.active === true
    }

    get liveToggleDisabled() {
        if (this.busy || !this.status) return true
        const manager = this.status.capture.manager
        if (!manager) return true
        return this.liveCaptureActive ? !manager.canStop : !manager.canStart
    }

    get localVisionInstalled() {
        return this.localVisionState === 'ok' || this.localVisionState === 'error'
    }

    get localVisionHealthy() {
        return this.localVisionState === 'ok'
    }

    get localVisionLabel() {
        return this.localVisionHealthy
            ? this.labels.localVisionOk
            : this.labels.localVisionError
    }

    number(value: number | null | undefined, digits: number) {
        return value === null || value === undefined || !Number.isFinite(value) ? '—' : value.toFixed(digits)
    }

    async refresh() {
        await Promise.all([this.refreshAutoPa(), this.refreshLocalVision()])
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
        } catch (error) {
            this.error = error instanceof Error ? error.message : String(error)
        }
    }

    async refreshLocalVision() {
        try {
            const response = await fetch('/local-vision/api/health', {
                cache: 'no-store',
                headers: { Accept: 'application/json' },
            })
            const contentType = response.headers.get('content-type') ?? ''
            if (response.status === 404 || (response.ok && !contentType.includes('application/json'))) {
                this.localVisionState = 'absent'
                return
            }
            if (!response.ok) {
                this.localVisionState = 'error'
                return
            }
            const health = (await response.json()) as {
                ok?: boolean
                service?: string
            }
            if (health.service !== 'local-vision-console') {
                this.localVisionState = 'absent'
                return
            }
            this.localVisionState = health.ok === true ? 'ok' : 'error'
        } catch (_error) {
            this.localVisionState = 'error'
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

    openLocalVision() {
        window.location.assign('/local-vision/')
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

.autopa-service-row {
    display: flex;
    align-items: center;
    min-height: 34px;
    padding: 6px 8px;
    border: 1px solid rgba(128, 128, 128, 0.2);
    border-radius: 4px;
    font-size: 0.78rem;
}

.autopa-service-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.autopa-service-row.healthy {
    color: var(--v-success-base);
}

.autopa-service-row.healthy .autopa-service-dot {
    background: var(--v-success-base);
    box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.14);
}

.autopa-service-row.failed {
    color: var(--v-error-base);
}

.autopa-service-row.failed .autopa-service-dot {
    background: var(--v-error-base);
    box-shadow: 0 0 0 3px rgba(244, 67, 54, 0.14);
}

.autopa-actions {
    display: flex;
    align-items: center;
    gap: 5px;
}

@media (max-width: 420px) {
    .autopa-sensors {
        grid-template-columns: 1fr;
    }

    .autopa-sensor {
        display: grid;
        grid-template-columns: 0.9fr 1fr 1.3fr;
        align-items: center;
        gap: 6px;
    }

    .autopa-sensor strong,
    .autopa-sensor small {
        margin-top: 0;
    }
}
</style>
