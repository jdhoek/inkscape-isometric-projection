#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import sys
import inkex
from inkex import Effect, Transform

sys.path.append('/usr/share/inkscape/extensions')
inkex.localization.localize()

def _apply_transform(elem, xform : Transform):
    """Apply a transform to an svg element, maintaining its center.
    Respects inkscape:transform-center-x/y attributes
    """
    #get the elements current position & transform center
    bbox_center = elem.bounding_box().center
    tcx = float(elem.get('inkscape:transform-center-x',0))
    tcy = -float(elem.get('inkscape:transform-center-y',0)) #NB inverted
    xform_center = bbox_center + (tcx,tcy)
    #compute the offset to keep the center stationary, then apply it
    offset = Transform().add_translate(xform_center - xform.apply_to_point(xform_center))
    xform = offset @ xform

    #compute any existing transform with the new one
    old_xform = Transform(elem.get('transform'))
    new_xform = xform @ old_xform

    #apply to the element
    elem.set('transform', new_xform)

    #update transform-center-x/y if necessary
    if tcx != 0 or tcy != 0:
        #we need to recompute the bounding box center as it will have changed
        #  NB the bounding box is non-linear as it is based on min & max
        #     coordinates, and min/max are non-linear operators. So we can't
        #     just use our linear transforms to find the new bounding box
        #     center. It's better to let inkscape do it internally :)
        new_bbox_center = elem.bounding_box().center
        new_tc = xform_center - new_bbox_center
        elem.set('inkscape:transform-center-x',f'{new_tc.x}')
        elem.set('inkscape:transform-center-y',f'{-new_tc.y}') #NB inverted

def _ar_to_xy(angle,radius):
    """Convert (angle, radius) to (x, y)"""
    return radius*math.cos(angle), radius*math.sin(angle)

def _projection_matrix(u_xy, v_xy, w_xy):
    """Create a projection matrix from 3D [u,v,w] to 2D screen coordinates [x,y]
    from the given u,v,w axes.
    Parameters u_xy,v_xy,w_xy are given in screen coordinates e.g. u_xy = [ux,uy]
    Returns a 2x3 matrix P = (ux,vx,wx, uy,vy,wy) such that x,y = ux*u + vx*v + wx*w, uy*u + vy*v + wy*w
    """
    (ux,uy),(vx,vy),(wx,wy) = u_xy, v_xy, w_xy
    return ux,vx,wx, uy,vy,wy

def _rotation_matrix(roll, pitch, yaw):
    """Create a rotation matrix from 2D screen coordinates [x,y] to 3D [u,v,w]
    according to Euler angles roll, pitch, and yaw, in radians.

    Euler angle order Z(yaw)Y(pitch)X(roll) (see https://en.wikipedia.org/wiki/Euler_angles)

    In standard inkscape coordinates, x = right, y = down, (which imply z = into the screen).
    Here, roll, pitch, and yaw correspond to "airplane" coordinates for a plane facing right (+x).
    +roll will tilt the right wing down "into the page" (from y to z)
    +pitch will tilt the nose up "out of the page" (from x to -z)
    +yaw will turn to the right (from x to y)

    Returns a 3x2 matrix R = (xu,yu, xv,yv, xw,yw) such that u,v,w = xu*x + yu*y, xv*x + yv*y, xw*x + yw*y
    i.e. [u, v, w] = R @ [x, y], treating [u,v,w] and [x,y] as column vectors
    NB xu is the u-component of x
    """
    c1,c2,c3 = math.cos(yaw), math.cos(pitch), math.cos(roll)
    s1,s2,s3 = math.sin(yaw), math.sin(pitch), math.sin(roll)
    xu,xv,xw = c1*c2, c2*s1, s2
    yu,yv,yw = c1*s2*s3 - c3*s1, c1*c3 + s1*s2*s3, c2*s3
    #zu,zv,zw = s1*s3 + c2*c3*s2, c3*s1*s2 - c1*s2, c2*c3 #for posterity
    return xu,yu, xv,yv, xw,yw

def _make_transform(projection, model):
    """Combine a 2x3 model matrix and 3x2 projection matrix into an svg Transform"""
    ux,vx,wx, uy,vy,wy = projection
    xu,yu, xv,yv, xw,yw = model
    #multiply the 2 matrices into a svg transform matrix
    #  this is equivalent to transforming [x1,y1] -> [u,v,w] -> [x2,y2]
    xx, xy = ux*xu + vx*xv + wx*xw, ux*yu + vx*yv + wx*yw
    yx, yy = uy*xu + vy*xv + wy*xw, uy*yu + vy*yv + wy*yw
    return Transform((xx,yx,xy,yy,0,0)) #svg matrix() order

class AxonometricProjectionEffect(Effect):
    """Apply an axonometric projection to a drawing element.
    Stores the projection parameters (model & projection matrices) in attribute DATA_ATTR
    """

    DATA_ATTR = 'axpr-data'
    
    @staticmethod
    def _format_data(*args, fmt='{:.6g}'):
        """format ((1,2,3),(4,5,6)) -> '1 2 3; 4 5 6'"""
        return '; '.join(' '.join(fmt.format(x) for x in arg) for arg in args)

    @classmethod
    def _set_data(cls, elem, data : str | None):
        """Set the element's data attribute to data, or delete the attribute if data is None."""
        if data is None:
            del elem.attrib[cls.DATA_ATTR]
        else:
            elem.set(cls.DATA_ATTR, data)

    @classmethod
    def _parse_data(cls, elem):
        """Parse the element's data attribute into tuples of numbers, or None"""
        data = elem.get(cls.DATA_ATTR)
        if data is not None:
            #parse '1 2 3; 4 5 6' -> ((1,2,3),(4,5,6))
            return tuple(tuple(float(v) for v in s.split()) for s in data.split(';'))
        return None

    def __init__(self):
        Effect.__init__(self)
        self.arg_parser.add_argument('--mode',choices=['apply','update-projection','update-model','remove'],default='apply',
                                     help='apply: apply the specified projection and model transforms, removing any prior axonometric transform,\n'
                                     +'update-projection: set only the projection axes, keeping the model pose unchanged,\n'
                                     +'update-model: set only the model pose, keeping the projection axes unchanged,\n'
                                     +'remove: remove any prior axonometric projection')
        self.arg_parser.add_argument('--projection-preset',choices=['none','isometric','dimetric'],default='none',
                                     help='none: projection axes are set manually by --{u/v/w}-{angle/scale} parameters,\n'
                                     +'isometric: projection axes are set to isometric, other projection parameters are ignored,\n'
                                     +'dimetric: projection axes are set to dimetric, --u-angle is used to set dimetric angle.')
        self.arg_parser.add_argument('--u-angle',type=float,default=-30, help='Projection u-axis angle (in degrees, inkscape screen coordinates)')
        self.arg_parser.add_argument('--v-angle',type=float,default=90, help='Projection v-axis angle (in degrees, inkscape screen coordinates)')
        self.arg_parser.add_argument('--w-angle',type=float,default=210, help='Projection w-axis angle (in degrees, inkscape screen coordinates)')
        self.arg_parser.add_argument('--u-scale',type=float,default=1, help='Projection u-axis scale')
        self.arg_parser.add_argument('--v-scale',type=float,default=1, help='Projection v-axis scale')
        self.arg_parser.add_argument('--w-scale',type=float,default=1, help='Projection w-axis scale')
        self.arg_parser.add_argument('--model-preset',choices=['none','top','left','right'],default='none',
                                     help='none: model pose is set manually by --{roll/pitch/yaw},\n'
                                     +'right: roll,pitch,yaw = 0,0,0; top: roll,pitch,yaw = 90,0,0; left: roll,pitch,yaw = 0,90,0')
        self.arg_parser.add_argument('--roll',type=float,default=0, help='Model roll, in degrees. Rotation about +x, rotates +y (down) into the page, before projection.')
        self.arg_parser.add_argument('--pitch',type=float,default=0, help='Model pitch, in degrees. Rotation about +y, rotates +x (right) out of the page, before projection.')
        self.arg_parser.add_argument('--yaw',type=float,default=0, help='Model yaw, in degrees. Rotation from +x to +y, before projection.')

    def _get_projection_matrix(self):
        ua, va, wa = self.options.u_angle, self.options.v_angle, self.options.w_angle
        us, vs, ws = self.options.u_scale, self.options.v_scale, self.options.w_scale
        if self.options.projection_preset == 'isometric':
            ua,va,wa = -30, 90, 210
            us,vs,ws = 1,1,1
        elif self.options.projection_preset == 'dimetric':
            ua,va,wa = ua, 90, 180-ua #ensure symmetry
            us,vs,ws = 1,1,1
        elif self.options.projection_preset != 'none':
            inkex.errormsg(f'Unknown projection preset "{self.options.projection_preset}", ignoring.')
        ua, va, wa = math.radians(ua), math.radians(va), math.radians(wa)
        return _projection_matrix(_ar_to_xy(ua,us),_ar_to_xy(va,vs),_ar_to_xy(wa,ws))

    def _get_model_matrix(self):
        roll, pitch, yaw = self.options.roll, self.options.pitch, self.options.yaw
        if self.options.model_preset == 'top':
            roll, pitch, yaw = 90, 0, 0
        elif self.options.model_preset == 'left':
            roll, pitch, yaw = 0, 90, 0
        elif self.options.model_preset == 'right':
            roll, pitch, yaw = 0, 0, 0
        elif self.options.model_preset != 'none':
            inkex.errormsg(f'Unknown model preset "{self.options.model_preset}", ignoring.')
        roll, pitch, yaw = math.radians(roll), math.radians(pitch), math.radians(yaw)
        return _rotation_matrix(roll, pitch, yaw)
    
    def effect(self):
        # deal with parameters
        mode = self.options.mode
        projection = self._get_projection_matrix()
        model = self._get_model_matrix()

        #precompute
        if mode == 'apply':
            pre_xform = _make_transform(projection, model)
            pre_data = self._format_data(projection, model)

        #apply the operation to each selected element
        for elem in self.svg.selection:
            #get any existing axonometric data
            old_data = self._parse_data(elem)

            if old_data is None:
                #the element isn't already axonometric
                if mode == 'remove':
                    continue #ignore
                elif mode.startswith('update'):
                    inkex.errormsg('Update on element that is not axonometric, ignoring')
                    continue
                old_xform = None
            else:
                old_proj, old_model = old_data
                old_xform = _make_transform(old_proj, old_model)

            if mode == 'apply':
                #use the pre-computed values
                xform, data = pre_xform, pre_data
            elif mode == 'remove':
                xform = Transform()
                data = None
            elif mode == 'update-projection':
                xform = _make_transform(projection, old_model)
                data = self._format_data(projection, old_model)
            elif mode == 'update-model':
                xform = _make_transform(old_proj, model)
                data = self._format_data(old_proj, model)
            else:
                inkex.errormsg(f'Unknown mode: "{mode}"')
                return

            # compose the new transform with the inverse of the old to remove it
            if old_xform is not None:
                xform = xform @ -old_xform

            # do it
            _apply_transform(elem, xform)
            self._set_data(elem, data)

# Create effect instance and apply it.
effect = AxonometricProjectionEffect()
effect.run()
