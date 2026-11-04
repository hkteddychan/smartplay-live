package com.opencode.pgodrive;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.widget.TextView;

/** Unused placeholder activity so the APK has a launcher entry. */
public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        TextView t = new TextView(this);
        t.setText("pgdrive driver");
        setContentView(t);
    }
}
