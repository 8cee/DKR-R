package com.eightcee.dkrrecomp;

import android.content.Context;
import android.hardware.input.InputManager;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;

final class ControllerBridge {
    private ControllerBridge() {}

    private static InputManager inputManager;
    private static final InputManager.InputDeviceListener DEVICE_LISTENER =
            new InputManager.InputDeviceListener() {
                @Override public void onInputDeviceAdded(int deviceId) {}
                @Override public void onInputDeviceChanged(int deviceId) {}
                @Override public void onInputDeviceRemoved(int deviceId) {
                    nativeRemoveDevice(deviceId);
                }
            };

    static native void nativeSetButton(int deviceId, int keyCode, boolean pressed);
    static native void nativeSetAxis(
            int deviceId, float lx, float ly, float rx, float ry, float lt, float rt);
    static native void nativeRemoveDevice(int deviceId);

    static void register(Context context) {
        if (inputManager != null) return;
        InputManager manager =
                (InputManager) context.getSystemService(Context.INPUT_SERVICE);
        if (manager == null) return;
        inputManager = manager;
        manager.registerInputDeviceListener(DEVICE_LISTENER, null);
    }

    static void unregister() {
        InputManager manager = inputManager;
        inputManager = null;
        if (manager != null) {
            manager.unregisterInputDeviceListener(DEVICE_LISTENER);
        }
    }

    static boolean handleKey(KeyEvent event) {
        if ((event.getSource() & InputDevice.SOURCE_GAMEPAD) == 0 &&
            (event.getSource() & InputDevice.SOURCE_JOYSTICK) == 0) return false;
        nativeSetButton(
                event.getDeviceId(), event.getKeyCode(),
                event.getAction() != KeyEvent.ACTION_UP);
        return true;
    }

    static boolean handleMotion(MotionEvent event) {
        if ((event.getSource() & InputDevice.SOURCE_JOYSTICK) == 0) return false;
        nativeSetAxis(
                event.getDeviceId(),
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
