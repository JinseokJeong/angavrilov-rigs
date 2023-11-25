# ====================== BEGIN GPL LICENSE BLOCK ======================
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ======================= END GPL LICENSE BLOCK ========================

# <pep8 compliant>

from math import pi
from mathutils import Vector

from rigify.utils.animation import add_generic_snap_fk_to_ik
from rigify.utils.bones import is_connected_position
from rigify.utils.naming import make_derived_name
from rigify.utils.switch_parent import SwitchParentBuilder
from rigify.utils.widgets_basic import create_shoulder_widget

from rigify.base_rig import stage

from .limb_rigs import BaseBodyIkLimbParentRig, BaseBodyIkArmRig


class Rig(BaseBodyIkLimbParentRig):
    """Shoulder bone with Body IK support."""

    def find_org_bones(self, pose_bone):
        return pose_bone.name

    arm_rig: BaseBodyIkArmRig

    def initialize(self):
        super().initialize()

        arms = [
            child for child in self.rigify_children
            if isinstance(child, BaseBodyIkArmRig)
        ]

        if len(arms) != 1:
            self.raise_error('IK shoulder must have one Body IK arm child.')

        self.arm_rig = arms[0]

        if not is_connected_position(self.obj, self.bones.org, self.arm_rig.bones.org.main[0]):
            self.raise_error('The shoulder bone and arm chain must be in a connected position.')

    ####################################################
    # BONES

    class CtrlBones(BaseBodyIkLimbParentRig.CtrlBones):
        master: str                    # Main control

    class MchBones(BaseBodyIkLimbParentRig.MchBones):
        ik: list[str]                  # IK chain
        ik_tgt: str                    # IK target

    bones: BaseBodyIkLimbParentRig.ToplevelBones[
        str,
        'Rig.CtrlBones',
        'Rig.MchBones',
        str
    ]

    ####################################################
    # Control bone

    @stage.generate_bones
    def make_control_bone(self):
        org = self.bones.org
        name = make_derived_name(org, 'ctrl')
        self.bones.ctrl.master = self.copy_bone(org, name, parent=True)

        parent = self.get_bone_parent(org)
        if parent:
            SwitchParentBuilder(self.generator).register_parent(self, parent)

    @stage.configure_bones
    def configure_control_bone(self):
        self.copy_bone_properties(self.bones.org, self.bones.ctrl.master)

        master = self.bones.ctrl.master
        arm_controls = self.arm_rig.get_snap_body_ik_controls()
        panel = self.script.panel_with_selected_check(
            self, self.bones.ctrl.flatten() + arm_controls)

        add_generic_snap_fk_to_ik(
            panel,
            fk_bones=[master],
            ik_bones=[self.bones.org],
            ik_ctrl_bones=[master],
            clear=False,
            label='Snap To IK', rig_name=master,
        )

    @stage.generate_widgets
    def make_control_widget(self):
        ctrl = self.bones.ctrl.master

        self.get_bone(ctrl).custom_shape_transform = self.get_bone(self.bones.org)

        create_shoulder_widget(self.obj, ctrl)

    ####################################################
    # Deform bone

    @stage.generate_bones
    def make_deform_bone(self):
        self.bones.deform = self.copy_bone(
            self.bones.org, make_derived_name(self.bones.org, 'def'))

    @stage.parent_bones
    def parent_deform_bone(self):
        self.set_bone_parent(self.bones.deform, self.bones.org)

    ####################################################
    # Org bone

    @stage.rig_bones
    def rig_org_bone(self):
        org = self.bones.org
        self.make_constraint(org, 'COPY_TRANSFORMS', self.bones.ctrl.master)

        con = self.make_constraint(org, 'DAMPED_TRACK', self.bones.mch.ik[1])
        self.make_driver(con, 'influence', variables=[(self.bones.mch.ik_tgt, 'influence')])

    def get_body_ik_safe_parent_bone(self):
        """Parent bone for Body IK child limbs that doesn't depend on the IK"""
        return self.bones.ctrl.master

    def get_body_ik_final_parent_bone(self):
        """Parent bone for Body IK child limbs that does depend on the IK"""
        return self.bones.org

    ####################################################
    # IK MCH chain

    @stage.generate_bones
    def make_ik_mch_chain(self):
        org = self.bones.org
        self.bones.mch.ik_tgt = self.copy_bone(
            org, make_derived_name(org, 'mch', '.ik_tgt'), scale=1/5)
        mch1 = self.copy_bone(org, make_derived_name(org, 'mch', '.ik'))
        mch2 = self.copy_bone(org, make_derived_name(org, 'mch', '.ik_end'))
        bone1 = self.get_bone(mch1)
        bone2 = self.get_bone(mch2)
        bone1.tail = bone2.head = bone1.head + Vector((0, 0, bone1.length))
        bone2.tail = bone2.head + Vector((1, 0, 0))
        bone1.roll = bone2.roll = 0
        bone2.inherit_scale = 'NONE'
        self.bones.mch.ik = [mch1, mch2]

    @stage.parent_bones
    def parent_ik_mch_chain(self):
        mch = self.bones.mch
        self.generator.disable_auto_parent(mch.ik[0])
        self.parent_bone_chain(mch.ik, use_connect=True)

    @stage.configure_bones
    def configure_ik_mch_chain(self):
        bone = self.get_bone(self.bones.mch.ik_tgt)
        bone['length'] = 1.0
        bone['influence'] = 0.0

    @stage.rig_bones
    def rig_ik_mch_chain(self):
        mch = self.bones.mch

        self.arm_rig.rig_body_ik_target_bone(mch.ik_tgt)

        self.make_driver(mch.ik[1], 'scale', index=1, variables=[(mch.ik_tgt, 'length')])

        self.rig_ik_system(mch.ik[0], mch.ik[1],  mch.ik_tgt, self.bones.ctrl.master)

    def rig_ik_system(self, mch_base: str, mch_ik: str, mch_tgt: str, ctrl: str):
        self.make_constraint(mch_base, 'COPY_LOCATION', ctrl)
        self.make_constraint(mch_base, 'DAMPED_TRACK', ctrl, head_tail=1)
        self.make_constraint(mch_base, 'COPY_SCALE', ctrl)
        self.make_constraint(
            mch_base, 'LOCKED_TRACK', mch_tgt,
            lock_axis='LOCK_Y', track_axis='TRACK_X',
        )

        bone_ik = self.get_bone(mch_ik)
        bone_ik.lock_ik_y = bone_ik.lock_ik_z = True
        bone_ik.use_ik_limit_x = True
        bone_ik.ik_min_x = -pi/2
        bone_ik.ik_max_x = pi/2

        self.make_constraint(
            mch_ik, 'IK', mch_tgt,
            chain_count=2, use_stretch=False,
        )
