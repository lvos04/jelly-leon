package test.b03.klok;

import android.app.Activity;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.os.Bundle;
import android.view.View;

/** Bekende klok voor adb-screencap, met de bitvolgorde en blokverhouding van het bevroren framecoderecept. */
public final class Meetklok extends Activity {
    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(new View(this) {
            private final Paint wit = new Paint();

            @Override
            protected void onDraw(Canvas canvas) {
                long frame = System.currentTimeMillis() * 24 / 1001;
                canvas.drawColor(Color.BLACK);
                wit.setColor(Color.WHITE);
                float breedte = getWidth() / 16f;
                for (int bit = 0; bit < 16; bit++) {
                    if ((frame & (1L << bit)) != 0) {
                        canvas.drawRect(bit * breedte, 0, (bit + .9f) * breedte, getHeight(), wit);
                    }
                }
                postInvalidateOnAnimation();
            }
        });
    }
}
