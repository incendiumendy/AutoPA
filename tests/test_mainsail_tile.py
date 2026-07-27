import json
import pathlib
import sys
import tempfile
import unittest


PROJECT_ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from mainsail_tile import prepare_mainsail_source


class MainsailTileTests(unittest.TestCase):
    def make_source(self, root, version="2.18.2"):
        source = pathlib.Path(root, "mainsail")
        (source / "src/pages").mkdir(parents=True)
        (source / "src/components/mixins").mkdir(parents=True)
        (source / "src/components/panels").mkdir(parents=True)
        (source / "src/store").mkdir(parents=True)
        (source / "package.json").write_text(
            json.dumps({"name": "mainsail", "version": version}),
            encoding="utf-8")
        (source / "src/pages/Dashboard.vue").write_text(
            "<script>\n"
            "import AfcPanel from '@/components/panels/AfcPanel.vue'\n"
            "@Component({\n"
            "    components: {\n"
            "        AfcPanel,\n"
            "    },\n"
            "})\n"
            "</script>\n",
            encoding="utf-8")
        (source / "src/store/variables.ts").write_text(
            "export const allDashboardPanels = [\n"
            "    'afc',\n"
            "    'webcam',\n"
            "]\n",
            encoding="utf-8")
        (source / "src/components/mixins/dashboard.ts").write_text(
            "import {\n"
            "    mdiMulticast,\n"
            "} from '@mdi/js'\n"
            "export class DashboardMixin {\n"
            "    getPanelName(name: string) {\n"
            "        if (name.startsWith('macrogroup_')) {\n"
            "            return 'Macrogroup'\n"
            "        }\n"
            "    }\n"
            "    convertPanelnameToIcon(name: string): string {\n"
            "        switch (name) {\n"
            "            case 'webcam':\n"
            "                return mdiMulticast\n"
            "        }\n"
            "    }\n"
            "}\n",
            encoding="utf-8")
        (source / "src/components/mixins/navigation.ts").write_text(
            "import { mdiLinkVariant, mdiViewDashboardOutline } from '@mdi/js'\n"
            "export class NavigationMixin {\n"
            "    private customNaviLinks = []\n"
            "    async sidebarNaviFileChanged(newVal: string) {\n"
            "        this.customNaviLinks = []\n"
            "\n"
            "        // stop if no file is set\n"
            "        if (!newVal) return\n"
            "\n"
            "        const content = await fetch(newVal)\n"
            "            .then((res) => res.json())\n"
            "            .catch((err) => {\n"
            "                window.console.error('Unable to parse .theme/navi.json.')\n"
            "                throw err\n"
            "            })\n"
            "\n"
            "        content.forEach((item: NaviPoint) => {\n"
            "            this.customNaviLinks.push(item)\n"
            "        })\n"
            "    }\n"
            "}\n",
            encoding="utf-8")
        return source

    def test_creates_separate_native_movable_panel_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_source(directory)
            output = pathlib.Path(directory, "patched")
            manifest = prepare_mainsail_source(source, output)
            self.assertEqual("2.18.2", manifest["mainsail_version"])
            self.assertFalse(manifest["source_modified"])
            self.assertFalse(
                (source / "src/components/panels/AutopaPanel.vue").exists())
            panel = (
                output / "src/components/panels/AutopaPanel.vue"
            ).read_text(encoding="utf-8")
            self.assertIn("/autopa/api/status", panel)
            self.assertIn("/local-vision/api/health", panel)
            self.assertIn("localVisionInstalled", panel)
            self.assertIn(
                "health.service !== 'local-vision-console'",
                panel)
            self.assertIn(
                "window.location.assign('/local-vision/')",
                panel)
            self.assertIn("Dry-Run ein", panel)
            self.assertIn("Live ein", panel)
            self.assertIn("/autopa/api/capture/${action}", panel)
            self.assertIn("Bewegung", panel)
            self.assertIn("Temperatur", panel)
            self.assertIn("autopa-context-line", panel)
            self.assertIn("PRESSURE_DISPLAY_DEADBAND = 0.1", panel)
            self.assertIn(
                "MOTION_DISPLAY_DEADBAND_MM_S2 = 200", panel)
            self.assertIn("this.status?.sensors.alps.state === 'ok'", panel)
            self.assertNotIn("SET_PRESSURE_ADVANCE", panel)
            dashboard = (
                output / "src/pages/Dashboard.vue"
            ).read_text(encoding="utf-8")
            self.assertIn("AutopaPanel", dashboard)
            variables = (
                output / "src/store/variables.ts"
            ).read_text(encoding="utf-8")
            self.assertIn("'autopa'", variables)
            mixin = (
                output / "src/components/mixins/dashboard.ts"
            ).read_text(encoding="utf-8")
            self.assertIn("name === 'autopa'", mixin)
            navigation = (
                output / "src/components/mixins/navigation.ts"
            ).read_text(encoding="utf-8")
            self.assertIn("href: '/autopa/'", navigation)
            self.assertIn("href: '/local-vision/'", navigation)
            self.assertIn(
                "if (!content.some((item) => item.href === link.href))",
                navigation)
            self.assertTrue(
                (output / ".autopa-mainsail-integration.json").is_file())
            public_manifest = json.loads(
                (output / "public/autopa-integration.json").read_text(
                    encoding="utf-8"))
            self.assertEqual("autopa", public_manifest["panel"])
            self.assertEqual(4, public_manifest["format_version"])
            self.assertEqual(
                "/local-vision/api/health",
                public_manifest["optional_health"]["local_vision"])
            self.assertEqual(
                ["/autopa/", "/local-vision/"],
                public_manifest["navigation_links"])
            self.assertEqual(
                "passive_capture_and_off_or_dry_run_only",
                public_manifest["control_policy"])
            self.assertNotIn("source", public_manifest)
            self.assertNotIn("output", public_manifest)

    def test_refuses_existing_output_and_unsupported_mainsail(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_source(directory, version="2.19.0")
            output = pathlib.Path(directory, "patched")
            with self.assertRaises(ValueError):
                prepare_mainsail_source(source, output)
            source = self.make_source(
                pathlib.Path(directory, "supported"), version="2.18.2")
            output.mkdir()
            with self.assertRaises(FileExistsError):
                prepare_mainsail_source(source, output)

    def test_refuses_output_inside_source_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_source(directory)
            with self.assertRaises(ValueError):
                prepare_mainsail_source(
                    source, source / "build/autopa")


if __name__ == "__main__":
    unittest.main()
