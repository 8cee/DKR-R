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
            entry.objects = ",".join(
                str(o) for o in issue.objects if o is not None
            )
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


class DKR_OT_select_issue(bpy.types.Operator):
    """Select the objects a validation result is about"""

    bl_idname = "dkr.select_issue"
    bl_label = "Select"
    bl_options = {"REGISTER", "UNDO"}

    objects: bpy.props.StringProperty(options={"HIDDEN"})

    def execute(self, context):
        wanted = {int(p) for p in self.objects.split(",") if p.strip().isdigit()}
        if not wanted:
            self.report({"WARNING"}, "this result does not name any object")
            return {"CANCELLED"}

        found = None
        for obj in scene.iter_dkr_objects(context):
            match = int(obj.get("dkr_order", -1)) in wanted
            obj.select_set(match)
            if match:
                found = obj
        if found is None:
            self.report({"ERROR"}, "those objects are no longer in the scene")
            return {"CANCELLED"}

        context.view_layer.objects.active = found
        # Frame them, since a duplicate is usually sitting exactly on top of the
        # object it was copied from and is invisible until the view moves.
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                with context.temp_override(area=area, region=area.regions[-1]):
                    try:
                        bpy.ops.view3d.view_selected()
                    except RuntimeError:
                        pass
                break
        self.report({"INFO"}, "selected %d object(s)" % len(wanted))
        return {"FINISHED"}


CLASSES = (DKR_OT_validate, DKR_OT_select_issue)
