"""Create a separate Mainsail source tree with the AutoPA dashboard panel."""
import argparse
import json
import shutil
from pathlib import Path


SUPPORTED_MAINSAIL_VERSIONS = {"2.18.2"}
INTEGRATION_VERSION = 4


def _replace_once(path, old, new):
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise ValueError(
            "%s: expected integration anchor exactly once, found %d"
            % (path, count))
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def _verify_source(source):
    required = [
        source / "package.json",
        source / "src/pages/Dashboard.vue",
        source / "src/components/mixins/dashboard.ts",
        source / "src/store/variables.ts",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError("not a complete Mainsail source tree: %s" % missing)
    package = json.loads(
        (source / "package.json").read_text(encoding="utf-8"))
    if package.get("name") != "mainsail":
        raise ValueError("source package is not Mainsail")
    version = str(package.get("version", ""))
    if version not in SUPPORTED_MAINSAIL_VERSIONS:
        raise ValueError(
            "unsupported Mainsail version %s; supported: %s"
            % (version or "unknown",
               ", ".join(sorted(SUPPORTED_MAINSAIL_VERSIONS))))
    return version


def prepare_mainsail_source(source_path, output_path, component_path=None):
    """Copy a pinned upstream tree, integrate AutoPA, and return a manifest."""
    source = Path(source_path).resolve()
    output = Path(output_path).resolve()
    component = (
        Path(component_path).resolve()
        if component_path else
        Path(__file__).resolve().parents[1]
        / "integrations/mainsail/AutopaPanel.vue")
    if source == output or source in output.parents:
        raise ValueError("output must be separate from the source tree")
    if output.exists():
        raise FileExistsError(output)
    if not component.is_file():
        raise FileNotFoundError(component)
    version = _verify_source(source)

    shutil.copytree(
        source, output,
        ignore=shutil.ignore_patterns(
            ".git", "node_modules", "dist", ".vite", "coverage"))
    target_component = (
        output / "src/components/panels/AutopaPanel.vue")
    shutil.copy2(component, target_component)

    dashboard = output / "src/pages/Dashboard.vue"
    _replace_once(
        dashboard,
        "import AfcPanel from '@/components/panels/AfcPanel.vue'\n",
        "import AfcPanel from '@/components/panels/AfcPanel.vue'\n"
        "import AutopaPanel from '@/components/panels/AutopaPanel.vue'\n")
    _replace_once(
        dashboard,
        "        AfcPanel,\n",
        "        AfcPanel,\n"
        "        AutopaPanel,\n")

    variables = output / "src/store/variables.ts"
    _replace_once(
        variables,
        "export const allDashboardPanels = [\n    'afc',\n",
        "export const allDashboardPanels = [\n"
        "    'afc',\n"
        "    'autopa',\n")

    mixin = output / "src/components/mixins/dashboard.ts"
    _replace_once(
        mixin,
        "    mdiMulticast,\n} from '@mdi/js'\n",
        "    mdiMulticast,\n"
        "    mdiChartTimelineVariant,\n"
        "} from '@mdi/js'\n")
    _replace_once(
        mixin,
        "    getPanelName(name: string) {\n"
        "        if (name.startsWith('macrogroup_')) {\n",
        "    getPanelName(name: string) {\n"
        "        if (name === 'autopa') return 'AutoPA'\n\n"
        "        if (name.startsWith('macrogroup_')) {\n")
    _replace_once(
        mixin,
        "        switch (name) {\n"
        "            case 'webcam':\n",
        "        switch (name) {\n"
        "            case 'autopa':\n"
        "                return mdiChartTimelineVariant\n"
        "            case 'webcam':\n")

    navigation = output / "src/components/mixins/navigation.ts"
    _replace_once(
        navigation,
        "import { mdiLinkVariant, mdiViewDashboardOutline } from '@mdi/js'\n",
        "import {\n"
        "    mdiChartTimelineVariant,\n"
        "    mdiEyeOutline,\n"
        "    mdiLinkVariant,\n"
        "    mdiViewDashboardOutline,\n"
        "} from '@mdi/js'\n")
    _replace_once(
        navigation,
        "        // stop if no file is set\n"
        "        if (!newVal) return\n\n"
        "        const content = await fetch(newVal)\n"
        "            .then((res) => res.json())\n"
        "            .catch((err) => {\n"
        "                window.console.error('Unable to parse .theme/navi.json.')\n"
        "                throw err\n"
        "            })\n\n"
        "        content.forEach((item: NaviPoint) => {\n",
        "        const content: NaviPoint[] = newVal\n"
        "            ? await fetch(newVal)\n"
        "                  .then((res) => res.json())\n"
        "                  .catch((err) => {\n"
        "                      window.console.error('Unable to parse .theme/navi.json.')\n"
        "                      throw err\n"
        "                  })\n"
        "            : []\n\n"
        "        const bundledLinks: NaviPoint[] = [\n"
        "            {\n"
        "                type: 'link',\n"
        "                title: 'AutoPA',\n"
        "                href: '/autopa/',\n"
        "                target: '',\n"
        "                position: 83,\n"
        "                icon: mdiChartTimelineVariant,\n"
        "                visible: true,\n"
        "            },\n"
        "            {\n"
        "                type: 'link',\n"
        "                title: 'Local Vision',\n"
        "                href: '/local-vision/',\n"
        "                target: '',\n"
        "                position: 84,\n"
        "                icon: mdiEyeOutline,\n"
        "                visible: true,\n"
        "            },\n"
        "        ]\n"
        "        bundledLinks.forEach((link) => {\n"
        "            if (!content.some((item) => item.href === link.href)) content.push(link)\n"
        "        })\n\n"
        "        content.forEach((item: NaviPoint) => {\n")

    manifest = {
        "format_version": INTEGRATION_VERSION,
        "mainsail_version": version,
        "source": str(source),
        "output": str(output),
        "panel": "autopa",
        "api": "/autopa/api/status",
        "optional_health": {
            "local_vision": "/local-vision/api/health",
        },
        "navigation_links": [
            "/autopa/",
            "/local-vision/",
        ],
        "control_policy": "passive_capture_and_off_or_dry_run_only",
        "source_modified": False,
    }
    public_dir = output / "public"
    public_dir.mkdir(exist_ok=True)
    public_manifest = {
        key: manifest[key]
        for key in (
            "format_version",
            "mainsail_version",
            "panel",
            "api",
            "optional_health",
            "navigation_links",
            "control_policy",
            "source_modified",
        )
    }
    (public_dir / "autopa-integration.json").write_text(
        json.dumps(public_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    (output / ".autopa-mainsail-integration.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create a separate Mainsail 2.18.2 source tree containing the "
            "native movable AutoPA panel. The upstream source is unchanged."))
    parser.add_argument("source", help="Clean upstream Mainsail source tree")
    parser.add_argument("output", help="New patched source tree")
    args = parser.parse_args()
    print(json.dumps(
        prepare_mainsail_source(args.source, args.output),
        indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
