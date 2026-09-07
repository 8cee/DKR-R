"""Run the pre-export checks and show what they found."""

from __future__ import annotations

import traceback

import bpy

from .. import catalog as catalog_module, scene, validate


class DKR_OT_validate(bpy.types.Operator):
    """Check the track for problems that are hard to diagnose in game"""

    bl_idname = "dkr.validate"
    bl_label = "Validate Track"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.dkr
        try:
            catalog = catalog_module.load()
            object_map = scene.export_object_map(context, catalog)
            report = validate.validate(
                object_map, catalog,
                require_racing_track=settings.is_racing_track,
            )
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, "validation failed: %s" % error)
            return {"CANCELLED"}

        settings.results.clear()
        for issue in report:
            entry = settings.results.add()
            entry.severity = issue.severity
            entry.message = issue.message
            entry.object_id = issue.object_id
        settings.has_validated = True

        if report.errors:
            self.report(
                {"ERROR"},
                "%d error(s), %d warning(s)" % (len(report.errors), len(report.warnings)),
            )
        elif report.warnings:
            self.report({"WARNING"}, "%d warning(s)" % len(report.warnings))
        else:
            self.report({"INFO"}, "no problems found")
        return {"FINISHED"}


CLASSES = (DKR_OT_validate,)
