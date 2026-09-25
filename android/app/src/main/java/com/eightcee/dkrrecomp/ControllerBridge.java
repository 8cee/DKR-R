package com.eightcee.dkrrecomp;

import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;

final class ControllerBridge {
    private ControllerBridge() {}

    static native void nativeSetButton(int keyCode, boolean pressed);
    static native void nativeSetAxis(float lx, float ly, float rx, float ry, float lt, float rt);

    static boolean handleKey(KeyEvent event) {
        if ((event.getSource() & InputDevice.SOURCE_GAMEPAD) == 0 &&
            (event.getSource() & InputDevice.SOURCE_JOYSTICK) == 0) return false;
        nativeSetButton(event.getKeyCode(), event.getAction() != KeyEvent.ACTION_UP);
        return true;
    }

    static boolean handleMotion(MotionEvent event) {
        if ((event.getSource() & InputDevice.SOURCE_JOYSTICK) == 0) return false;
        nativeSetAxis(
                axis(event, MotionEvent.AXIS_X),
                axis(event, MotionEvent.AXIS_Y),
                axis(event, MotionEvent.AXIS_Z),
                axis(event, MotionEvent.AXIS_RZ),
                Math.max(axis(event, MotionEvent.AXIS_LTRIGGER), axis(event, MotionEvent.AXIS_BRAKE)),
                Math.max(axis(event, MotionEvent.AXIS_RTRIGGER), axis(event, MotionEvent.AXIS_GAS)));
        return true;
    }

    private static float axis(MotionEvent e, int axis) {
        InputDevice device=e.getDevice();
        if (device==null) return 0f;
        InputDevice.MotionRange r=device.getMotionRange(axis,e.getSource());
        if (r==null) return 0f;
        float v=e.getAxisValue(axis);
        float flat=r.getFlat();
        return Math.abs(v)>flat?v:0f;
    }
}
