#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
sys.path.append('/usr/share/inkscape/extensions')

import inkex
inkex.localize()

from simpletransform import * 
from simplestyle import *

import math

class IsometricProjectionTools(inkex.Effect):
    """
    Convert a flat 2D projection to one of the three visible sides in an
    isometric projection, and vice versa.
    """

    # Precomputed values for sine, cosine, and tangent of 30°.
    rad_30 = math.radians(30)
    cos_30 = math.cos(rad_30)
    sin_30 = 0.5 # No point in using math.sin for 30°.
    tan_30 = math.tan(rad_30)

    # Combined affine transformation matrices. The bottom row of these 3×3
    # matrices is omitted; it is always [0, 0, 1].
    transformations = {
        # From 2D to isometric top down view:
        #   * scale vertically by cos(30°)
        #   * shear horizontally by -30°
        #   * rotate clock-wise 30°
        'to_top':       [[cos_30,       -cos_30,    0], 
                         [sin_30,       sin_30,     0]],

        # From 2D to isometric left-hand side view:
        #   * scale horizontally by cos(30°)
        #   * shear vertically by -30°
        'to_left':      [[cos_30,       0,          0],
                         [sin_30,       1,          0]],

        # From 2D to isometric right-hand side view:
        #   * scale horizontally by cos(30°)
        #   * shear vertically by 30°
        'to_right':     [[cos_30,       0,          0],
                         [-sin_30,      1,          0]],

        # From isometric top down view to 2D:
        #   * rotate counter-clock-wise 30°
        #   * shear horizontally by 30°
        #   * scale vertically by 1 / cos(30°)
        'from_top':     [[tan_30,       1,          0],
                         [-tan_30,      1,          0]],

        # From isometric left-hand side view to 2D:
        #   * shear vertically by 30°
        #   * scale horizontally by 1 / cos(30°)
        'from_left':    [[1 / cos_30,   0,          0],
                         [-tan_30,      1,          0]],

        # From isometric right-hand side view to 2D:
        #   * shear vertically by -30°
        #   * scale horizontally by 1 / cos(30°)
        'from_right':   [[1 / cos_30,   0,          0],
                         [tan_30,       1,          0]]
    }

    def __init__(self):
        """
        Constructor.
        """

        inkex.Effect.__init__(self)

        self.OptionParser.add_option('-c', '--conversion', action = 'store',
                type = 'string', dest = 'conversion', default = 'top',
                help = 'Conversion to perform: (top|left|right)')
        self.OptionParser.add_option('-r', '--reverse', action = 'store',
                type = 'string', dest = 'reverse', default = "false",
                help = 'Reverse the transformation from isometric projection '
                       'to flat 2D')

    def effect(self):
        """
        Apply the transformation. If an element already has a transformation
        attribute, it will be combined with the transformation matrix for the
        requested conversion.
        """
       
        if self.options.reverse == "true":
            conversion = "from_" + self.options.conversion
        else:
            conversion = "to_" + self.options.conversion

        if len(self.selected) == 0:
            inkex.errormsg(_("Please select an object to perform the " +
                    "isometric projection transformation on."))
            return

        # Default to the flat 2D to isometric top down view conversion if an
        # invalid identifier is passed.
        effect_matrix = self.transformations.get(
                conversion, self.transformations.get('to_top'))

        for id, node in self.selected.iteritems():
            transform = node.get("transform")
            # Combine our transformation matrix with any pre-existing
            # transform.
            matrix = parseTransform(transform, effect_matrix)
            node.set('transform', formatTransform(matrix))    

# Create effect instance and apply it.
effect = IsometricProjectionTools()
effect.affect()
