package com.eightcee.dkrrecomp;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.view.MotionEvent;
import android.view.View;

import java.util.HashMap;
import java.util.Map;

final class VirtualPadView extends View {
    private static final int DEVICE_ID = 0x7F000001;

    private static final int KEY_A = 96;
    private static final int KEY_B = 99;
    private static final int KEY_Z = 104;
    private static final int KEY_L = 102;
    private static final int KEY_R = 103;
    private static final int KEY_START = 108;
    private static final int KEY_C_UP = 100;
    private static final int KEY_C_RIGHT = 97;
    private static final int KEY_C_DOWN = 105;

    // Match the DK64 Android pad language: dark translucent glass with
    // N64-colored accents, thin borders, soft glow and a bright stick knob.
    private static final int GLASS = 0xFF0A0D12;
    private static final int TINT_A = 0xFF7FB2E5;
    private static final int TINT_B = 0xFF63C46B;
    private static final int TINT_C = 0xFFF6DC7A;
    private static final int TINT_START = 0xFFF2707F;
    private static final int TINT_NEUTRAL = 0xFFE8ECEF;
    private static final int ACCENT = 0xFF9BD32B;

    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path arrow = new Path();
    private final Map<Integer, Control> pointers = new HashMap<>();

    private final Control a = new Control("A", KEY_A, TINT_A, false, 0f);
    private final Control b = new Control("B", KEY_B, TINT_B, false, 0f);
    private final Control z = new Control("Z", KEY_Z, TINT_NEUTRAL, false, 0f);
    private final Control l = new Control("L", KEY_L, TINT_NEUTRAL, false, 0f);
    private final Control r = new Control("R", KEY_R, TINT_NEUTRAL, false, 0f);
    private final Control start = new Control("START", KEY_START, TINT_START, false, 0f);
    private final Control menu = new Control("MENU", -2, TINT_NEUTRAL, false, 0f);
    private final Control cu = new Control("", KEY_C_UP, TINT_C, true, -90f);
    private final Control cr = new Control("", KEY_C_RIGHT, TINT_C, true, 0f);
    private final Control cd = new Control("", KEY_C_DOWN, TINT_C, true, 90f);
    private final Control cl = new Control("", -1, TINT_C, true, 180f);

    private float unit = 1f;
    private float stickCx, stickCy, stickRadius, stickKnobRadius;
    private int stickPointer = -1;
    private float stickX, stickY;
    private boolean cLeft;
    private boolean visiblePad;
    private boolean menuMode;

    private static final class Control {
        final String label;
        final int keyCode;
        final int tint;
        final boolean arrow;
        final float arrowAngle;
        float x, y, radius;
        boolean pressed;
        Shader glass;
        Shader shadow;
        Shader glow;

        Control(String label, int keyCode, int tint, boolean arrow, float arrowAngle) {
            this.label = label;
            this.keyCode = keyCode;
            this.tint = tint;
            this.arrow = arrow;
            this.arrowAngle = arrowAngle;
        }

        boolean hit(float px, float py) {
            float dx = px - x, dy = py - y;
            float rr = radius * 1.45f;
            return dx * dx + dy * dy <= rr * rr;
        }
    }

    VirtualPadView(Context context) {
        super(context);
        setWillNotDraw(false);
        setBackgroundColor(Color.TRANSPARENT);
        visiblePad = context.getSharedPreferences("dkr_virtual_pad", Context.MODE_PRIVATE)
                .getBoolean("visible", false);

        stroke.setStyle(Paint.Style.STROKE);
        stroke.setStrokeCap(Paint.Cap.ROUND);
        stroke.setStrokeJoin(Paint.Join.ROUND);

        text.setTextAlign(Paint.Align.CENTER);
        text.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
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
        unit = Math.min(w / 1280f, h / 720f);
        stickCx = w * 0.13f;
        stickCy = h * 0.70f;
        stickRadius = 96f * unit;
        stickKnobRadius = 47f * unit;

        layout(a, w * 0.89f, h * 0.66f, 54f * unit);
        layout(b, w * 0.79f, h * 0.77f, 39f * unit);
        layout(cu, w * 0.78f, h * 0.39f, 34f * unit);
        layout(cd, w * 0.78f, h * 0.55f, 34f * unit);
        layout(cl, w * 0.71f, h * 0.47f, 34f * unit);
        layout(cr, w * 0.85f, h * 0.47f, 34f * unit);
        layout(start, w * 0.50f, h * 0.86f, 35f * unit);
        layout(menu, w * 0.64f, h * 0.87f, 31f * unit);
        layout(z, w * 0.12f, h * 0.12f, 43f * unit);
        layout(l, w * 0.42f, h * 0.10f, 41f * unit);
        layout(r, w * 0.88f, h * 0.10f, 41f * unit);

        rebuildShaders(new Control[]{a,b,cu,cd,cl,cr,start,menu,z,l,r});
    }

    private static void layout(Control c, float x, float y, float radius) {
        c.x = x;
        c.y = y;
        c.radius = radius;
    }

    private void rebuildShaders(Control[] controls) {
        for (Control c : controls) {
            c.glass = new LinearGradient(c.x, c.y - c.radius, c.x, c.y + c.radius,
                    new int[]{0x26FFFFFF, 0x08FFFFFF}, null, Shader.TileMode.CLAMP);
            c.shadow = new RadialGradient(c.x, c.y, c.radius * 1.5f,
                    new int[]{0x59000000, Color.TRANSPARENT}, null, Shader.TileMode.CLAMP);
            c.glow = new RadialGradient(c.x, c.y, c.radius * 1.38f,
                    new int[]{Color.TRANSPARENT, c.tint, Color.TRANSPARENT},
                    new float[]{0.5f, 0.86f, 1f}, Shader.TileMode.CLAMP);
        }
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (!visiblePad) return;

        syncMenuMode();
        if (menuMode) {
            drawControl(canvas, menu);
            return;
        }

        drawStick(canvas);
        drawControl(canvas, a);
        drawControl(canvas, b);
        drawControl(canvas, cu);
        drawControl(canvas, cd);
        drawControl(canvas, cl);
        drawControl(canvas, cr);
        drawControl(canvas, start);
        drawControl(canvas, menu);
        drawControl(canvas, z);
        drawControl(canvas, l);
        drawControl(canvas, r);
    }

    private void drawControl(Canvas canvas, Control c) {
        final float scale = c.pressed ? 0.94f : 1f;
        canvas.save();
        canvas.scale(scale, scale, c.x, c.y);

        if (c.shadow != null) {
            fill.setShader(c.shadow);
            fill.setAlpha(255);
            canvas.drawCircle(c.x, c.y, c.radius * 1.5f, fill);
            fill.setShader(null);
        }

        fill.setStyle(Paint.Style.FILL);
        fill.setShader(null);
        fill.setColor(GLASS);
        fill.setAlpha(145);
        canvas.drawCircle(c.x, c.y, c.radius, fill);

        if (c.glass != null) {
            fill.setShader(c.glass);
            fill.setAlpha(255);
            canvas.drawCircle(c.x, c.y, c.radius, fill);
            fill.setShader(null);
        }

        if (c.pressed && c.glow != null) {
            fill.setShader(c.glow);
            fill.setAlpha(205);
            canvas.drawCircle(c.x, c.y, c.radius * 1.38f, fill);
            fill.setShader(null);

            fill.setColor(Color.WHITE);
            fill.setAlpha(38);
            canvas.drawCircle(c.x, c.y, c.radius, fill);
        }

        stroke.setStrokeWidth(2.5f * unit);
        stroke.setColor(c.pressed ? Color.WHITE : c.tint);
        stroke.setAlpha(c.pressed ? 255 : 120);
        canvas.drawCircle(c.x, c.y, c.radius, stroke);

        final int contentColor = c.pressed ? Color.WHITE : c.tint;
        if (c.arrow) {
            fill.setColor(contentColor);
            fill.setAlpha(c.pressed ? 255 : 220);
            drawArrow(canvas, c.x, c.y, c.radius * 0.55f, c.arrowAngle);
        } else if (c == menu) {
            stroke.setStrokeWidth(Math.max(2f * unit, c.radius * 0.13f));
            stroke.setColor(contentColor);
            stroke.setAlpha(c.pressed ? 255 : 220);
            float half = c.radius * 0.48f;
            float gap = c.radius * 0.30f;
            for (int i = -1; i <= 1; ++i) {
                canvas.drawLine(c.x - half, c.y + i * gap,
                        c.x + half, c.y + i * gap, stroke);
            }
        } else {
            text.setColor(contentColor);
            text.setAlpha(c.pressed ? 255 : 225);
            text.setTextSize(Math.max(18f * unit,
                    c.radius * (c.label.length() > 2 ? 0.52f : 0.82f)));
            canvas.drawText(c.label, c.x,
                    c.y - (text.ascent() + text.descent()) / 2f, text);
        }

        canvas.restore();
        fill.setAlpha(255);
        stroke.setAlpha(255);
        text.setAlpha(255);
    }

    private void drawStick(Canvas canvas) {
        Shader shadow = new RadialGradient(stickCx, stickCy, stickRadius * 1.45f,
                new int[]{0x59000000, Color.TRANSPARENT}, null, Shader.TileMode.CLAMP);
        fill.setShader(shadow);
        fill.setAlpha(255);
        canvas.drawCircle(stickCx, stickCy, stickRadius * 1.45f, fill);
        fill.setShader(null);

        fill.setColor(GLASS);
        fill.setAlpha(145);
        canvas.drawCircle(stickCx, stickCy, stickRadius, fill);

        Shader glass = new LinearGradient(stickCx, stickCy - stickRadius,
                stickCx, stickCy + stickRadius,
                new int[]{0x26FFFFFF, 0x08FFFFFF}, null, Shader.TileMode.CLAMP);
        fill.setShader(glass);
        fill.setAlpha(255);
        canvas.drawCircle(stickCx, stickCy, stickRadius, fill);
        fill.setShader(null);

        stroke.setStrokeWidth(2f * unit);
        for (int i = 0; i < 8; ++i) {
            double angle = Math.toRadians(i * 45.0);
            float ca = (float)Math.cos(angle);
            float sa = (float)Math.sin(angle);
            float inner = stickRadius * 0.76f;
            float outer = stickRadius * 0.88f;
            stroke.setColor(Color.WHITE);
            stroke.setAlpha(72);
            canvas.drawLine(stickCx + ca * inner, stickCy + sa * inner,
                    stickCx + ca * outer, stickCy + sa * outer, stroke);
        }

        stroke.setStrokeWidth(2.5f * unit);
        stroke.setColor(stickPointer >= 0 ? ACCENT : TINT_NEUTRAL);
        stroke.setAlpha(stickPointer >= 0 ? 255 : 120);
        canvas.drawCircle(stickCx, stickCy, stickRadius, stroke);

        float travel = (stickRadius - stickKnobRadius) * 0.92f;
        float kx = stickCx + stickX * travel;
        float ky = stickCy - stickY * travel;

        fill.setColor(Color.BLACK);
        fill.setAlpha(45);
        canvas.drawCircle(kx, ky, stickKnobRadius * 1.18f, fill);

        fill.setColor(GLASS);
        fill.setAlpha(220);
        canvas.drawCircle(kx, ky, stickKnobRadius, fill);

        Shader knob = new RadialGradient(kx, ky, stickKnobRadius,
                new int[]{0x36FFFFFF, 0x08000000}, null, Shader.TileMode.CLAMP);
        fill.setShader(knob);
        fill.setAlpha(255);
        canvas.drawCircle(kx, ky, stickKnobRadius, fill);
        fill.setShader(null);

        stroke.setStrokeWidth(2f * unit);
        stroke.setColor(Color.WHITE);
        stroke.setAlpha(75);
        canvas.drawCircle(kx, ky, stickKnobRadius * 0.66f, stroke);

        stroke.setStrokeWidth(2.5f * unit);
        stroke.setColor(stickPointer >= 0 ? ACCENT : TINT_NEUTRAL);
        stroke.setAlpha(stickPointer >= 0 ? 255 : 125);
        canvas.drawCircle(kx, ky, stickKnobRadius, stroke);

        fill.setAlpha(255);
        stroke.setAlpha(255);
    }

    private void drawArrow(Canvas canvas, float x, float y, float size, float angleDeg) {
        float ang = (float)Math.toRadians(angleDeg);
        float tipX = x + size * (float)Math.cos(ang);
        float tipY = y + size * (float)Math.sin(ang);
        float a1 = ang + 2.5f;
        float a2 = ang - 2.5f;
        arrow.reset();
        arrow.moveTo(tipX, tipY);
        arrow.lineTo(x + size * 0.45f * (float)Math.cos(a1),
                y + size * 0.45f * (float)Math.sin(a1));
        arrow.lineTo(x + size * 0.45f * (float)Math.cos(a2),
                y + size * 0.45f * (float)Math.sin(a2));
        arrow.close();
        canvas.drawPath(arrow, fill);
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
