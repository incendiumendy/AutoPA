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

        <v-card-text class="py-3">
            <div class="d-flex align-center mb-3">
                <span class="autopa-live-dot mr-2" :class="{ live: isLive }" />
                <strong>{{ statusLabel }}</strong>
                <v-spacer />
                <v-chip x-small outlined :color="modeColor">{{ modeLabel }}</v-chip>
            </div>

            <v-alert v-if="error" dense text type="warning" class="mb-3">
                {{ labels.unavailable }}
            </v-alert>

            <div v-if="status" class="autopa-grid">
                <div>
                    <span>{{ labels.pressure }}</span>
                    <strong>{{ pressureLabel }}</strong>
                </div>
                <div>
                    <span>PA</span>
                    <strong>{{ number(status.printer.pressureAdvance, 3) }}</strong>
                </div>
                <div>
                    <span>{{ labels.layer }}</span>
                    <strong>{{ contextLayer }}</strong>
                </div>
                <div>
                    <span>{{ labels.feature }}</span>
                    <strong>{{ featureLabel }}</strong>
                </div>
                <div>
                    <span>{{ labels.speed }}</span>
                    <strong>{{ speedLabel }}</strong>
                </div>
                <div>
                    <span>{{ labels.flow }}</span>
                    <strong>{{ flowLabel }}</strong>
                </div>
            </div>

            <div class="autopa-window mt-3" :class="{ eligible: paWindowActive }">
                {{ contextStateLabel }}
            </div>

            <div class="d-flex mt-3">
                <v-btn
                    small
                    outlined
                    color="primary"
                    :disabled="busy || !status || applyActive"
                    @click="toggleDryRun">
                    {{ dryRunActive ? labels.disable : labels.enable }}
                </v-btn>
                <v-spacer />
                <v-btn small text color="primary" @click="openDashboard">
                    {{ labels.open }}
                </v-btn>
            </div>

            <p v-if="applyActive" class="caption warning--text mt-2 mb-0">
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
        pressureAdvance: number | null
    }
    capture: {
        state: string
        ageSeconds: number | null
    }
    sensors: {
        alps: {
            state: string
            normalized: number | null
        }
    }
    quality: {
        state: string
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

    status: AutoPaStatus | null = null
    error = ''
    busy = false
    timer: number | null = null

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
                  layer: 'Layer',
                  feature: 'Feature',
                  speed: 'Geschwindigkeit',
                  flow: 'Volumenstrom',
                  enable: 'Dry-Run ein',
                  disable: 'Ausschalten',
                  open: 'AutoPA öffnen',
                  waiting: 'Wartet auf Live-Daten',
                  live: 'Live-Daten aktiv',
                  applyNotice: 'Bewaffneter Modus kann nur in AutoPA beendet werden.',
                  windowActive: 'PA-Messfenster aktiv',
                  windowIgnored: 'PA-Messfenster ignoriert',
                  contextMissing: 'Kein ausgeführter G-Code-Kontext',
              }
            : {
                  unavailable: 'AutoPA is unavailable. Printing continues unchanged.',
                  pressure: 'Nozzle load',
                  layer: 'Layer',
                  feature: 'Feature',
                  speed: 'Speed',
                  flow: 'Volumetric flow',
                  enable: 'Enable dry-run',
                  disable: 'Turn off',
                  open: 'Open AutoPA',
                  waiting: 'Waiting for live data',
                  live: 'Live data active',
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
        return value === null || value === undefined ? '—' : `${Math.round(value * 100)} %`
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

    number(value: number | null | undefined, digits: number) {
        return value === null || value === undefined || !Number.isFinite(value) ? '—' : value.toFixed(digits)
    }

    async refresh() {
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

    async toggleDryRun() {
        if (!this.status || this.applyActive) return
        this.busy = true
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

    openDashboard() {
        window.location.assign('/autopa/')
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

.autopa-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
}

.autopa-grid > div {
    min-width: 0;
    padding: 8px;
    border: 1px solid rgba(128, 128, 128, 0.2);
    border-radius: 4px;
}

.autopa-grid span,
.autopa-grid strong {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.autopa-grid span {
    color: var(--v-secondary-lighten2);
    font-size: 0.72rem;
}

.autopa-grid strong {
    margin-top: 2px;
    font-size: 0.88rem;
}

.autopa-window {
    padding: 7px 9px;
    border-left: 3px solid var(--v-warning-base);
    border-radius: 3px;
    background: rgba(255, 152, 0, 0.07);
    color: var(--v-warning-base);
    font-size: 0.78rem;
}

.autopa-window.eligible {
    border-left-color: var(--v-success-base);
    background: rgba(76, 175, 80, 0.07);
    color: var(--v-success-base);
}
</style>
