package com.eightcee.dkrrecomp;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.MotionEvent;
import android.view.View;

import java.util.HashMap;
import java.util.Map;

final class VirtualPadView extends View {
    private static final int DEVICE_ID = 0x7F000001;

    private static final int KEY_A = 96;
    private static final int KEY_B = 99;      // Android X -> N64 B in bridge
    private static final int KEY_Z = 104;     // L2 -> Z
    private static final int KEY_L = 102;
    private static final int KEY_R = 103;
    private static final int KEY_START = 108;
    private static final int KEY_C_UP = 100;  // Android Y -> C-Up
    private static final int KEY_C_RIGHT = 97;// Android B -> C-Right
    private static final int KEY_C_DOWN = 105;// Android R2 -> C-Down

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Map<Integer, Control> pointers = new HashMap<>();

    private final Control a = new Control("A", KEY_A);
    private final Control b = new Control("B", KEY_B);
    private final Control z = new Control("Z", KEY_Z);
    private final Control l = new Control("L", KEY_L);
    private final Control r = new Control("R", KEY_R);
    private final Control start = new Control("START", KEY_START);
    private final Control menu = new Control("MENU", -2);
    private final Control cu = new Control("C↑", KEY_C_UP);
    private final Control cr = new Control("C→", KEY_C_RIGHT);
    private final Control cd = new Control("C↓", KEY_C_DOWN);
    private final Control cl = new Control("C←", -1);

    private float stickCx, stickCy, stickRadius;
    private int stickPointer = -1;
    private float stickX, stickY;
    private boolean cLeft;
    private boolean visiblePad;
    private boolean menuMode;

    private static final class Control {
        final String label;
        final int keyCode;
        float x, y, radius;
        boolean pressed;
        Control(String label, int keyCode) {
            this.label = label;
            this.keyCode = keyCode;
        }
        boolean hit(float px, float py) {
            float dx = px - x, dy = py - y;
            return dx * dx + dy * dy <= radius * radius * 1.55f;
        }
    }

    VirtualPadView(Context context) {
        super(context);
        setWillNotDraw(false);
        setBackgroundColor(0x00000000);
        visiblePad = context.getSharedPreferences("dkr_virtual_pad", Context.MODE_PRIVATE)
                .getBoolean("visible", false);
        text.setTextAlign(Paint.Align.CENTER);
        text.setFakeBoldText(true);
        setContentDescription("DKR-R touchscreen controls");
    }

    void setPadVisible(boolean visible) {
        if (visiblePad == visible) return;
        visiblePad = visible;
        getContext().getSharedPreferences("dkr_virtual_pad", Context.MODE_PRIVATE)
                .edit().putBoolean("visible", visible).apply();
        if (!visible) releaseAll();
        invalidate();
    }

    boolean isPadVisible() {
        return visiblePad;
    }

    void releaseInput() {
        releaseAll();
    }

    @Override protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        float unit = Math.min(w / 1280f, h / 720f);
        stickCx = w * 0.13f;
        stickCy = h * 0.70f;
        stickRadius = 95f * unit;

        layout(a, w * 0.89f, h * 0.66f, 58f * unit);
        layout(b, w * 0.79f, h * 0.77f, 53f * unit);
        layout(cu, w * 0.78f, h * 0.39f, 37f * unit);
        layout(cd, w * 0.78f, h * 0.55f, 37f * unit);
        layout(cl, w * 0.71f, h * 0.47f, 37f * unit);
        layout(cr, w * 0.85f, h * 0.47f, 37f * unit);
        layout(start, w * 0.50f, h * 0.86f, 42f * unit);
        layout(menu, w * 0.64f, h * 0.87f, 38f * unit);
        layout(z, w * 0.12f, h * 0.12f, 48f * unit);
        layout(l, w * 0.42f, h * 0.10f, 44f * unit);
        layout(r, w * 0.88f, h * 0.10f, 44f * unit);
    }

    private static void layout(Control c, float x, float y, float radius) {
        c.x = x; c.y = y; c.radius = radius;
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (!visiblePad) return;

        syncMenuMode();
        if (menuMode) {
            drawControl(canvas, menu, 0xCC6F7A86);
            return;
        }

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(0x55101620);
        canvas.drawCircle(stickCx, stickCy, stickRadius, paint);
        paint.setColor(0xAAE8EEF5);
        canvas.drawCircle(stickCx + stickX * stickRadius * 0.62f,
                stickCy - stickY * stickRadius * 0.62f,
                stickRadius * 0.38f, paint);

        drawControl(canvas, a, 0xAA4E9CEB);
        drawControl(canvas, b, 0xAA4CAF50);
        drawControl(canvas, cu, 0xAADABF32);
        drawControl(canvas, cd, 0xAADABF32);
        drawControl(canvas, cl, 0xAADABF32);
        drawControl(canvas, cr, 0xAADABF32);
        drawControl(canvas, start, 0xAAE05A67);
        drawControl(canvas, menu, 0xAA6F7A86);
        drawControl(canvas, z, 0xAA88929E);
        drawControl(canvas, l, 0xAA88929E);
        drawControl(canvas, r, 0xAA88929E);
    }

    private void drawControl(Canvas canvas, Control c, int color) {
        paint.setColor(c.pressed ? (color | 0xFF000000) : color);
        canvas.drawCircle(c.x, c.y, c.radius, paint);
        text.setColor(0xFFFFFFFF);
        text.setTextSize(Math.max(18f, c.radius * (c.label.length() > 2 ? 0.52f : 0.78f)));
        canvas.drawText(c.label, c.x, c.y - (text.ascent() + text.descent()) / 2f, text);
    }

    @Override public boolean onTouchEvent(MotionEvent event) {
        if (!visiblePad) return false;
        syncMenuMode();
        int action = event.getActionMasked();
        int index = event.getActionIndex();
        int pointerId = event.getPointerId(index);

        if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_POINTER_DOWN) {
            float x = event.getX(index), y = event.getY(index);
            if (menuMode) {
                if (menu.hit(x, y)) {
                    pointers.put(pointerId, menu);
                    press(menu, true);
                    return true;
                }
                return false;
            }
            if (hitStick(x, y) && stickPointer < 0) {
                stickPointer = pointerId;
                updateStick(x, y);
                return true;
            }
            Control control = hitControl(x, y);
            if (control != null) {
                pointers.put(pointerId, control);
                press(control, true);
                return true;
            }
            return false;
        }

        if (action == MotionEvent.ACTION_MOVE) {
            for (int i = 0; i < event.getPointerCount(); ++i) {
                int id = event.getPointerId(i);
                if (id == stickPointer) {
                    updateStick(event.getX(i), event.getY(i));
                }
            }
            return stickPointer >= 0 || !pointers.isEmpty();
        }

        if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_POINTER_UP) {
            if (pointerId == stickPointer) {
                stickPointer = -1;
                stickX = stickY = 0f;
                publishAxes();
            }
            Control control = pointers.remove(pointerId);
            if (control != null) press(control, false);
            invalidate();
            return true;
        }

        if (action == MotionEvent.ACTION_CANCEL) {
            releaseAll();
            return true;
        }
        return true;
    }

    private boolean hitStick(float x, float y) {
        float dx = x - stickCx, dy = y - stickCy;
        float rr = stickRadius * 1.35f;
        return dx * dx + dy * dy <= rr * rr;
    }

    private Control hitControl(float x, float y) {
        Control[] controls = {a,b,cu,cd,cl,cr,start,menu,z,l,r};
        for (Control c : controls) if (c.hit(x, y)) return c;
        return null;
    }

    private void updateStick(float x, float y) {
        float dx = (x - stickCx) / stickRadius;
        float dy = (stickCy - y) / stickRadius;
        float length = (float)Math.sqrt(dx * dx + dy * dy);
        if (length > 1f) { dx /= length; dy /= length; }
        stickX = dx;
        stickY = dy;
        publishAxes();
        invalidate();
    }

    private void press(Control c, boolean pressed) {
        if (c.pressed == pressed) return;
        c.pressed = pressed;
        if (c == cl) {
            cLeft = pressed;
            publishAxes();
        } else if (c == menu) {
            if (pressed) {
                releaseGameplayControls();
                ControllerBridge.nativeToggleOverlay();
                menuMode = ControllerBridge.nativeOverlayVisible();
            }
        } else if (c.keyCode >= 0) {
            ControllerBridge.nativeSetButton(DEVICE_ID, c.keyCode, pressed);
        }
        invalidate();
    }

    private void publishAxes() {
        float rightX = cLeft ? -1f : 0f;
        ControllerBridge.nativeSetAxis(
                DEVICE_ID, stickX, -stickY, rightX, 0f, 0f, 0f);
    }

    private void syncMenuMode() {
        final boolean nativeVisible = ControllerBridge.nativeOverlayVisible();
        if (menuMode != nativeVisible) {
            if (nativeVisible) releaseGameplayControls();
            menuMode = nativeVisible;
        }
    }

    private void releaseGameplayControls() {
        for (Control c : new Control[]{a,b,cu,cd,cl,cr,start,z,l,r}) {
            if (c.pressed) {
                c.pressed = false;
                if (c == cl) {
                    cLeft = false;
                } else if (c.keyCode >= 0) {
                    ControllerBridge.nativeSetButton(DEVICE_ID, c.keyCode, false);
                }
            }
        }
        pointers.entrySet().removeIf(entry -> entry.getValue() != menu);
        stickPointer = -1;
        stickX = stickY = 0f;
        cLeft = false;
        ControllerBridge.nativeSetAxis(DEVICE_ID, 0f,0f,0f,0f,0f,0f);
    }

    private void releaseAll() {
        releaseGameplayControls();
        if (menu.pressed) menu.pressed = false;
        pointers.clear();
        menuMode = false;
        ControllerBridge.nativeRemoveDevice(DEVICE_ID);
        invalidate();
    }
}
