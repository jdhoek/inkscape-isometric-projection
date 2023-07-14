#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import sys
import inkex
from inkex.transforms import Transform

sys.path.append('/usr/share/inkscape/extensions')
inkex.localization.localize()


class IsometricProjectionTools(inkex.Effect):
    """
    Convert a flat 2D projection to one of the three visible sides in an
    isometric projection, and vice versa.
    """

    attrTransformCenterX = inkex.addNS('transform-center-x', 'inkscape')
    attrTransformCenterY = inkex.addNS('transform-center-y', 'inkscape')


    def __init__(self):
        """
        Constructor.
        """

        inkex.Effect.__init__(self)

        self.arg_parser.add_argument(
            '-c', '--conversion',
            dest='conversion', default='top',
            help='Conversion to perform: (top|left|right)')
        # Note: adding `type=bool` for the reverse option seems to break it when used
        # from within Inkscape. Not sure why.
        self.arg_parser.add_argument(
            '-r', '--reverse',
            dest='reverse', default="false",
            help='Reverse the transformation from isometric projection '
            'to flat 2D')
        self.arg_parser.add_argument(
            '-i', '--orthoangle_1', type=float,
            dest='orthoangle_1', default="30",
            help='Angle in degrees')
        self.arg_parser.add_argument(
            '-j', '--orthoangle_2', type=float,
            dest='orthoangle_2',
            help='Second angle in degrees, for dimetric projections')


    def __initConstants(self, angle_1, angle_2):
        angle_left = angle_1

        self.rad_l = math.radians(angle_left)
        self.cos_l = math.cos(self.rad_l)
        self.sin_l = math.sin(self.rad_l)

        if angle_2 is None or angle_2 == angle_1:
            # Dimetric, where the two angles are the same. This includes the 30° isometric view.
            self.rad_r = self.rad_l
            self.cos_r = self.cos_l
            self.sin_r = self.sin_l
            self.top_c = -self.cos_l
            self.top_d = self.sin_l
        else:
            # Trimetric, where the left and right angle differ.
            angle_right = angle_2
            self.rad_r = math.radians(angle_right)
            self.cos_r = math.cos(self.rad_r)
            self.sin_r = math.sin(self.rad_r)

            # Combined values for trimetric transform of top piece.
            self.rad_lp_r = math.radians(angle_left + angle_right)
            self.sin_lp_r = math.sin(self.rad_lp_r)
            self.shear_factor_top = math.sin(self.rad_lp_r)
            self.tan_shear_top = math.tan(self.rad_l + self.rad_r - math.pi / 2)

            self.top_c = self.shear_factor_top * (self.cos_l * self.tan_shear_top - self.sin_l)
            self.top_d = self.shear_factor_top * (self.sin_l * self.tan_shear_top + self.cos_l)

        # Combined affine transformation matrices. The bottom row of these 3×3
        # matrices is omitted; it is always [0, 0, 1].
        self.transformations = {
            # From 2D to isometric top down view (dimetric, isometric):
            #   * scale vertically by cos(∠)
            #   * shear horizontally by -∠
            #   * rotate clock-wise ∠
            #
            # From 2D to isometric top down view (trimetric):
            #   * scale vertically by sin(∠(left) + ∠(right)
            #   * shear horizontally by ∠(left) + ∠(right) - 90°
            #   * rotate clock-wise ∠
            'to_top':       Transform(((self.cos_l,        self.top_c,       0),
                                       (self.sin_l,        self.top_d,       0))),

            # From 2D to axonometric left-hand side view:
            #   * scale horizontally by cos(∠)
            #   * shear vertically by -∠
            'to_left':      Transform(((self.cos_l,        0,                0),
                                       (self.sin_l,        1,                0))),

            # From 2D to axonometric right-hand side view:
            #   * scale horizontally by cos(∠)
            #   * shear vertically by ∠
            'to_right':     Transform(((self.cos_r ,       0,                0),
                                       (-self.sin_r,       1,                0)))
        }

        # The inverse matrices of the above perform the reverse transformations.
        self.transformations['from_top'] = -self.transformations['to_top']
        self.transformations['from_left'] = -self.transformations['to_left']
        self.transformations['from_right'] = -self.transformations['to_right']

    def getTransformCenter(self, midpoint, node):
        """
        Find the transformation center of an object. If the user set it
        manually by dragging it in Inkscape, those coordinates are used.
        Otherwise, an attempt is made to find the center of the object's
        bounding box.
        """

        c_x = node.get(self.attrTransformCenterX)
        c_y = node.get(self.attrTransformCenterY)

        # Default to dead-center.
        if c_x is None:
            c_x = 0.0
        else:
            c_x = float(c_x)
        if c_y is None:
            c_y = 0.0
        else:
            c_y = float(c_y)

        x = midpoint[0] + c_x
        y = midpoint[1] - c_y

        return [x, y]

    def translateBetweenPoints(self, tr, here, there):
        """
        Add a translation to a matrix that moves between two points.
        """

        x = there[0] - here[0]
        y = there[1] - here[1]
        tr.add_translate(x, y)

    def moveTransformationCenter(self, node, midpoint, center_new):
        """
        If a transformation center is manually set on the node, move it to
        match the transformation performed on the node.
        """

        c_x = node.get(self.attrTransformCenterX)
        c_y = node.get(self.attrTransformCenterY)

        if c_x is not None:
            x = str(center_new[0] - midpoint[0])
            node.set(self.attrTransformCenterX, x)
        if c_y is not None:
            y = str(midpoint[1] - center_new[1])
            node.set(self.attrTransformCenterY, y)

    def effect(self):
        """
        Apply the transformation. If an element already has a transformation
        attribute, it will be combined with the transformation matrix for the
        requested conversion.
        """

        self.__initConstants(self.options.orthoangle_1, self.options.orthoangle_2)

        if self.options.reverse == "true":
            conversion = "from_" + self.options.conversion
        else:
            conversion = "to_" + self.options.conversion

        if len(self.svg.selected) == 0:
            inkex.errormsg(_("Please select an object to perform the "
                             "isometric projection transformation on."))
            return

        # Default to the flat 2D to isometric top down view conversion if an
        # invalid identifier is passed.
        effect_matrix = self.transformations.get(
            conversion, self.transformations.get('to_top'))

        for id, node in self.svg.selected.items():
            bbox = node.bounding_box()
            midpoint = [bbox.center_x, bbox.center_y]
            center_old = self.getTransformCenter(midpoint, node)
            transform = Transform(node.get("transform"))
            # Combine our transformation matrix with any pre-existing
            # transform.
            tr = transform @ effect_matrix

            # Compute the location of the transformation center after applying
            # the transformation matrix.
            center_new = center_old[:]
            #Transform(matrix).apply_to_point(center_new)
            tr.apply_to_point(center_new)
            tr.apply_to_point(midpoint)

            # Add a translation transformation that will move the object to
            # keep its transformation center in the same place.
            self.translateBetweenPoints(tr, center_new, center_old)

            node.set('transform', str(tr))

            # Adjust the transformation center.
            self.moveTransformationCenter(node, midpoint, center_new)

# Create effect instance and apply it.
effect = IsometricProjectionTools()
effect.run()
