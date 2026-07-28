<template>
    <panel
        :icon="mdiEyeOutline"
        title="Local Vision"
        :collapsible="true"
        card-class="localvision-panel"
        :loading="busy">
        <template #buttons>
            <v-btn icon tile :aria-label="labels.open" @click="openLocalVision">
                <v-icon>{{ mdiOpenInNew }}</v-icon>
            </v-btn>
        </template>

        <v-card-text class="localvision-body py-2">
            <div class="d-flex align-center mb-2">
                <span
                    class="localvision-dot mr-2"
                    :class="{ healthy: serviceHealthy, failed: !serviceHealthy }" />
                <strong>{{ serviceLabel }}</strong>
                <v-spacer />
                <v-chip x-small outlined :color="statusColor">{{ statusChip }}</v-chip>
            </div>

            <v-alert v-if="displayError" dense text type="warning" class="mb-2">
                {{ displayError }}
            </v-alert>

            <div class="localvision-calibration-title mb-2">
                <strong>{{ labels.calibration }}</strong>
                <small>{{ labels.console }}</small>
            </div>

            <div class="localvision-facts">
                <div>
                    <span>{{ labels.bed }}</span>
                    <strong>{{ bedLabel }}</strong>
                </div>
                <div>
                    <span>{{ labels.homing }}</span>
                    <strong>G28</strong>
                    <small>{{ labels.noHeat }}</small>
                </div>
                <div>
                    <span>{{ labels.points }}</span>
                    <strong>{{ pointCountLabel }}</strong>
                    <small>{{ labels.safeLimits }}</small>
                </div>
            </div>

            <div class="localvision-message mt-2">
                {{ message || labels.ready }}
            </div>

            <v-checkbox
                v-model="motionConfirmed"
                dense
                hide-details
                class="mt-2"
                :disabled="busy || !serviceHealthy"
                :label="labels.confirm" />

            <div class="localvision-actions mt-2">
                <v-btn
                    x-small
                    outlined
                    :disabled="busy || !serviceHealthy"
                    @click="checkPlan">
                    {{ labels.check }}
                </v-btn>
                <v-spacer />
                <v-btn
                    x-small
                    color="warning"
                    :disabled="busy || !serviceHealthy || !motionConfirmed"
                    @click="startCalibration">
                    {{ labels.start }}
                </v-btn>
            </div>
        </v-card-text>
    </panel>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import { mdiEyeOutline, mdiOpenInNew } from '@mdi/js'
import BaseMixin from '@/components/mixins/base'
import Panel from '@/components/ui/Panel.vue'

interface CalibrationPoint {
    name: string
    x: number
    y: number
}

interface CalibrationPlan {
    bedWidth: number
    bedDepth: number
    safeZ: number
    homedAxes: string
    points: CalibrationPoint[]
}

interface PlanResponse {
    ok: boolean
    nozzleHeatingRequired: boolean
    homingCommand: string
    plan: CalibrationPlan
}

@Component({
    components: { Panel },
})
export default class LocalvisionPanel extends Mixins(BaseMixin) {
    mdiEyeOutline = mdiEyeOutline
    mdiOpenInNew = mdiOpenInNew

    serviceHealthy = false
    calibrated = false
    busy = false
    motionConfirmed = false
    serviceError = ''
    actionError = ''
    message = ''
    plan: CalibrationPlan | null = null
    timer: number | null = null

    mounted() {
        void this.refresh()
        this.timer = window.setInterval(() => {
            if (!this.busy) void this.refresh()
        }, 5000)
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
                  unavailable: 'Dienst nicht erreichbar',
                  available: 'Dienst bereit',
                  calibration: 'Automatische Kamerakalibrierung',
                  bed: 'Druckbett',
                  homing: 'Homing',
                  noHeat: 'ohne Heizen',
                  points: 'Messpunkte',
                  safeLimits: 'innerhalb der Grenzen',
                  console: 'Fortschritt erscheint in der Mainsail-Konsole.',
                  ready: 'Plan prüfen, am Drucker bleiben und den Start ausdrücklich bestätigen.',
                  confirm: 'Ich bin am Drucker und bestätige Homing und Bewegungen.',
                  check: 'Plan prüfen',
                  start: 'Kalibrierung starten',
                  open: 'Local Vision öffnen',
                  calibrated: 'KALIBRIERT',
                  notCalibrated: 'NICHT KALIBRIERT',
                  running: 'LÄUFT',
              }
            : {
                  unavailable: 'Service unavailable',
                  available: 'Service ready',
                  calibration: 'Automatic camera calibration',
                  bed: 'Print bed',
                  homing: 'Homing',
                  noHeat: 'without heating',
                  points: 'Measurement points',
                  safeLimits: 'inside live limits',
                  console: 'Progress is shown in the Mainsail console.',
                  ready: 'Check the plan, stay at the printer and explicitly confirm the start.',
                  confirm: 'I am at the printer and confirm homing and movement.',
                  check: 'Check plan',
                  start: 'Start calibration',
                  open: 'Open Local Vision',
                  calibrated: 'CALIBRATED',
                  notCalibrated: 'NOT CALIBRATED',
                  running: 'RUNNING',
              }
    }

    get serviceLabel() {
        if (!this.serviceHealthy) return this.labels.unavailable
        return this.labels.available
    }

    get displayError() {
        return this.actionError || this.serviceError
    }

    get statusChip() {
        if (!this.serviceHealthy) return this.isGerman ? 'FEHLER' : 'ERROR'
        if (this.busy) return this.labels.running
        return this.calibrated ? this.labels.calibrated : this.labels.notCalibrated
    }

    get statusColor() {
        if (!this.serviceHealthy) return 'error'
        if (this.busy) return 'warning'
        return this.calibrated ? 'success' : 'warning'
    }

    get bedLabel() {
        if (!this.plan) return '—'
        return `${this.plan.bedWidth} × ${this.plan.bedDepth} mm`
    }

    get pointCountLabel() {
        return this.plan ? String(this.plan.points.length) : '5'
    }

    async request(path: string, options: RequestInit = {}) {
        const response = await fetch(path, {
            cache: 'no-store',
            ...options,
            headers: {
                Accept: 'application/json',
                ...(options.body ? { 'Content-Type': 'application/json' } : {}),
                ...(options.headers ?? {}),
            },
        })
        const payload = (await response.json().catch(() => ({}))) as {
            error?: string
            [key: string]: unknown
        }
        if (!response.ok) throw new Error(payload.error ?? `HTTP ${response.status}`)
        return payload
    }

    async refresh() {
        try {
            const [health, config] = await Promise.all([
                this.request('/local-vision/api/health'),
                this.request('/local-vision/api/config'),
            ])
            this.serviceHealthy =
                health.ok === true && health.service === 'local-vision-console'
            this.calibrated = config.cameraCalibrationConfigured === true
            this.serviceError = ''
        } catch (error) {
            this.serviceHealthy = false
            this.serviceError = error instanceof Error ? error.message : String(error)
        }
    }

    async checkPlan(): Promise<PlanResponse | null> {
        this.busy = true
        this.actionError = ''
        this.message = this.isGerman
            ? 'Klipper-Zustand und Achsgrenzen werden gelesen …'
            : 'Reading Klipper state and axis limits …'
        try {
            const response = (await this.request(
                '/local-vision/api/camera/calibration/plan')) as unknown as PlanResponse
            this.plan = response.plan
            if (response.homingCommand !== 'G28' || response.nozzleHeatingRequired) {
                throw new Error(
                    this.isGerman
                        ? 'Der sichere Plan erwartet G28 ohne Heizen.'
                        : 'The safe plan must use G28 without heating.')
            }
            this.message = this.isGerman
                ? `Plan bereit: ${this.bedLabel}, Z ${this.plan.safeZ} mm, ${this.plan.points.length} Punkte.`
                : `Plan ready: ${this.bedLabel}, Z ${this.plan.safeZ} mm, ${this.plan.points.length} points.`
            return response
        } catch (error) {
            this.actionError = error instanceof Error ? error.message : String(error)
            return null
        } finally {
            this.busy = false
        }
    }

    async startCalibration() {
        if (!this.motionConfirmed) return
        this.actionError = ''
        try {
            const preview = await this.checkPlan()
            if (!preview) return
            const points = preview.plan.points
                .map((point) => `${point.name}: X${point.x} Y${point.y}`)
                .join('\n')
            const confirmed = window.confirm(
                (this.isGerman
                    ? 'Automatische Kamerakalibrierung startet jetzt G28 ohne Heizen.'
                    : 'Automatic camera calibration will now start G28 without heating.')
                    + `\n\n${this.bedLabel}\nZ ${preview.plan.safeZ} mm\n${points}\n\n`
                    + (this.isGerman
                        ? 'Der Drucker muss leer und beaufsichtigt sein. Jetzt starten?'
                        : 'The printer must be clear and supervised. Start now?'),
            )
            if (!confirmed) {
                this.motionConfirmed = false
                this.message = this.isGerman
                    ? 'Vor jeder Bewegung abgebrochen.'
                    : 'Cancelled before any movement.'
                return
            }
            this.busy = true
            this.message = this.isGerman
                ? 'Kalibrierung läuft. Fortschritt steht in der Mainsail-Konsole …'
                : 'Calibration is running. Progress is shown in the Mainsail console …'
            const prepared = await this.request(
                '/local-vision/api/camera/calibration/prepare',
                {
                    method: 'POST',
                    body: JSON.stringify({ motionConfirmation: 'HOME_AND_MOVE' }),
                },
            )
            const result = await this.request('/local-vision/api/camera/calibration/run', {
                method: 'POST',
                body: JSON.stringify({
                    sessionToken: prepared.sessionToken,
                    motionConfirmation: 'HOME_AND_MOVE',
                }),
            })
            this.calibrated = true
            this.motionConfirmed = false
            this.message = this.isGerman
                ? `Kalibrierung gespeichert. Kontrollabweichung ${(
                      Number(result.reprojectionError) * 100
                  ).toFixed(1)} %.`
                : `Calibration saved. Check error ${(
                      Number(result.reprojectionError) * 100
                  ).toFixed(1)} %.`
        } catch (error) {
            this.actionError = error instanceof Error ? error.message : String(error)
        } finally {
            this.busy = false
        }
    }

    openLocalVision() {
        window.location.assign('/local-vision/')
    }
}
</script>

<style scoped>
.localvision-body {
    font-size: 0.8rem;
}

.localvision-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
}

.localvision-dot.healthy {
    background: var(--v-success-base);
    box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.14);
}

.localvision-dot.failed {
    background: var(--v-error-base);
    box-shadow: 0 0 0 3px rgba(244, 67, 54, 0.14);
}

.localvision-calibration-title {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
}

.localvision-calibration-title small {
    color: var(--v-secondary-lighten1);
    font-size: 0.65rem;
}

.localvision-facts {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 5px;
}

.localvision-facts > div {
    min-width: 0;
    padding: 6px 7px;
    border: 1px solid rgba(128, 128, 128, 0.2);
    border-radius: 4px;
}

.localvision-facts span,
.localvision-facts strong,
.localvision-facts small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.localvision-facts span,
.localvision-facts small {
    color: var(--v-secondary-lighten1);
    font-size: 0.65rem;
}

.localvision-facts strong {
    margin: 1px 0;
    color: var(--v-warning-base);
    font-size: 0.83rem;
}

.localvision-message {
    min-height: 32px;
    padding: 7px 9px;
    border-left: 3px solid var(--v-warning-base);
    border-radius: 3px;
    background: rgba(255, 152, 0, 0.07);
    color: var(--v-secondary-lighten2);
    font-size: 0.72rem;
}

.localvision-actions {
    display: flex;
    align-items: center;
}

@media (max-width: 420px) {
    .localvision-facts {
        grid-template-columns: 1fr;
    }

    .localvision-calibration-title {
        display: block;
    }

    .localvision-calibration-title small {
        display: block;
        margin-top: 2px;
    }
}
</style>
