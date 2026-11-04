package com.opencode.pgodrive;

import android.app.Instrumentation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.util.Log;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

/**
 * Layer-level driver for the PGSharp client.
 *
 * Runs as an instrumentation so it can talk to the accessibility node tree
 * directly:
 *   - read the tree with every label + bounds (no screencap needed)
 *   - click a node with AccessibilityNodeInfo.ACTION_CLICK, i.e. a real
 *     layer-level click, not a blind coordinate tap
 *
 * Host protocol (files on the device's /sdcard):
 *   /sdcard/pgo_cmd.txt   one command line
 *   /sdcard/pgo_out.txt   the reply
 *   /sdcard/pgo_busy      heartbeat, proves the driver is alive
 *
 * Commands:
 *   ping
 *   dump                          -> list every node: cls|text|desc|l,t,r,b|flags
 *   click_text <text>             -> ACTION_CLICK on the first matching node
 *   click <x> <y>                 -> real touch at that point
 *   swipe <x1> <y1> <x2> <y2> <ms>
 *   text <text>                   -> text of the first matching node
 */
public class Driver extends Instrumentation {

    public static final String TAG = "PGDRIVE";
    private String CMD_FILE;
    private String OUT_FILE;
    private String BUSY;

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        // The app's own external files dir: writable by the app AND by adb shell.
        File base = getContext().getExternalFilesDir(null);
        if (base == null) base = getContext().getFilesDir();
        if (!base.exists()) base.mkdirs();
        CMD_FILE = new File(base, "cmd.txt").getAbsolutePath();
        OUT_FILE = new File(base, "out.txt").getAbsolutePath();
        BUSY = new File(base, "busy").getAbsolutePath();
        Log.i(TAG, "driver files in " + base);
        try {
            // Without these flags the service only sees "important" windows
            // and Unity's surface is invisible to us.
            AccessibilityServiceInfo info = getUiAutomation().getServiceInfo();
            info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
                    | AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
                    | AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
            getUiAutomation().setServiceInfo(info);
            Log.i(TAG, "service info flags=" + info.flags);
        } catch (Throwable e) {
            Log.e(TAG, "serviceinfo", e);
        }
        start();
        Thread t = new Thread(this::loop);
        t.setDaemon(true);
        t.start();
    }

    private void loop() {
        sleep(500);
        while (true) {
            try {
                File busy = new File(BUSY);
                if (!busy.exists() || busy.lastModified() < System.currentTimeMillis() - 15000) {
                    busy.createNewFile();
                    busy.setLastModified(System.currentTimeMillis());
                }
                File cmd = new File(CMD_FILE);
                if (cmd.exists() && cmd.length() > 0) {
                    String line = read(cmd);
                    if (line != null && line.trim().length() > 0) {
                        cmd.delete();
                        String res;
                        try {
                            res = handle(line.trim());
                        } catch (Throwable e) {
                            res = "ERR " + e;
                        }
                        write(new File(OUT_FILE), res);
                        Log.i(TAG, "RESULT " + res);
                    }
                }
                sleep(40);
            } catch (Throwable e) {
                Log.e(TAG, "loop", e);
                sleep(400);
            }
        }
    }

    private String handle(String line) throws Exception {
        String[] parts = line.split("\\s+");
        String cmd = parts[0].toLowerCase();
        StringBuilder sb = new StringBuilder();

        switch (cmd) {
            case "ping":
                sb.append("OK pong");
                break;

            case "wins": {
                java.util.List<AccessibilityWindowInfo> ws = getUiAutomation().getWindows();
                sb.append("OK windows=").append(ws.size()).append('\n');
                for (AccessibilityWindowInfo w : ws) {
                    android.graphics.Rect b = new android.graphics.Rect();
                    w.getBoundsInScreen(b);
                    sb.append("win id=").append(w.getId())
                      .append(" type=").append(w.getType())
                      .append(" active=").append(w.isActive())
                      .append(" focus=").append(w.isFocused())
                      .append(" b=").append(b.left).append(',').append(b.top)
                      .append(',').append(b.right).append(',').append(b.bottom)
                      .append('\n');
                }
                break;
            }

            case "dump": {
                List<AccessibilityNodeInfo> all = new ArrayList<>();
                // The game's window is not always the "active" one (our own
                // activity or an overlay may hold focus), so walk every window.
                for (AccessibilityWindowInfo w : getUiAutomation().getWindows()) {
                    walk(w.getRoot(), all);
                }
                walk(getUiAutomation().getRootInActiveWindow(), all);
                sb.append("OK nodes=").append(all.size()).append('\n');
                for (AccessibilityNodeInfo n : all) {
                    sb.append(desc(n)).append('\n');
                }
                break;
            }

            case "imgs": {
                // just the images on the left floating bar (spawn shortcuts)
                List<AccessibilityNodeInfo> all = new ArrayList<>();
                for (AccessibilityWindowInfo w : getUiAutomation().getWindows()) {
                    walk(w.getRoot(), all);
                }
                walk(getUiAutomation().getRootInActiveWindow(), all);
                int n = 0;
                for (AccessibilityNodeInfo x : all) {
                    String cls = x.getClassName() == null ? "" : x.getClassName().toString();
                    if (!cls.endsWith("ImageView") && !cls.endsWith("ImageButton")) continue;
                    android.graphics.Rect b = new android.graphics.Rect();
                    x.getBoundsInScreen(b);
                    if (b.left > 200) continue;      // only the left column
                    sb.append(desc(x)).append('\n');
                    n++;
                }
                sb.append("OK images=").append(n);
                break;
            }

            case "click_text": {
                String want = argAfter(line);
                AccessibilityNodeInfo root = getUiAutomation().getRootInActiveWindow();
                AccessibilityNodeInfo hit = findText(root, want);
                if (hit == null) {
                    sb.append("ERR notfound ").append(want);
                } else {
                    boolean ok = hit.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    sb.append(ok ? "OK clicked " : "ERR clickfailed ").append(want)
                      .append(' ').append(desc(hit));
                }
                break;
            }

            case "text": {
                String want = argAfter(line);
                AccessibilityNodeInfo root = getUiAutomation().getRootInActiveWindow();
                AccessibilityNodeInfo hit = findText(root, want);
                sb.append(hit == null ? "ERR notfound " : "OK ").append(want);
                if (hit != null) sb.append(' ').append(desc(hit));
                break;
            }

            case "info": {
                // Full state of the first node whose text/desc contains <want>:
                // text|clickable|checkable|checked|bounds|class.  Lets the host
                // decide from data instead of guessing coordinates.
                String want = argAfter(line);
                AccessibilityNodeInfo hit = findText(getUiAutomation().getRootInActiveWindow(), want);
                if (hit == null) {
                    sb.append("ERR notfound ").append(want);
                } else {
                    sb.append("OK ").append(hit.getText() == null ? "" : hit.getText())
                      .append("|clickable=").append(hit.isClickable())
                      .append("|checkable=").append(hit.isCheckable())
                      .append("|checked=").append(hit.isChecked())
                      .append('|').append(desc(hit));
                }
                break;
            }
            case "toggle": {
                // Semantic click: no coordinates involved.  Finds the row that
                // owns <want>, then clicks its checkable Switch (which may be
                // scrolled off-screen and therefore impossible to tap).
                String want = argAfter(line);
                AccessibilityNodeInfo hit = findText(getUiAutomation().getRootInActiveWindow(), want);
                if (hit == null) {
                    sb.append("ERR notfound ").append(want);
                    break;
                }
                AccessibilityNodeInfo sw = findCheckable(hit);
                if (sw == null) sw = findCheckableUp(hit);
                if (sw == null) {
                    sb.append("ERR noconstrol ").append(want);
                } else {
                    boolean ok = sw.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    // NOTE: sw.isChecked() is still the pre-click value here
                    // (the node is not refreshed yet), so we do not report it.
                    sb.append(ok ? "OK toggled " : "ERR togglefailed ").append(want);
                }
                break;
            }

            case "clicknode": {
                // Semantic click on the clickable ancestor of <want>.
                String want = argAfter(line);
                AccessibilityNodeInfo hit = findText(getUiAutomation().getRootInActiveWindow(), want);
                if (hit == null) {
                    sb.append("ERR notfound ").append(want);
                    break;
                }
                AccessibilityNodeInfo target = hit;
                while (target != null && !target.isClickable()) target = target.getParent();
                boolean ok = target != null
                        && target.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                sb.append(ok ? "OK clicked_node " : "ERR clicknode_failed ").append(want);
                break;
            }

            case "index_click": {
                // Semantic click on the N-th clickable node (1-based) inside the
                // left strip.  Works even though the PGSharp nearby list has no
                // text at all -- we address it by data-layer enumeration order.
                int idx = Integer.parseInt(parts[1]);
                int leftmax = parts.length > 2 ? Integer.parseInt(parts[2]) : 130;
                List<AccessibilityNodeInfo> list =
                        clickables(getUiAutomation().getRootInActiveWindow(), leftmax);
                if (idx < 1 || idx > list.size()) {
                    sb.append("ERR index ").append(idx).append(" of ").append(list.size());
                } else {
                    AccessibilityNodeInfo n = list.get(idx - 1);
                    boolean ok = n.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    sb.append(ok ? "OK index_click " : "ERR index_click_failed ")
                      .append(idx).append(' ').append(desc(n));
                }
                break;
            }

            case "clickables": {
                int leftmax = parts.length > 1 ? Integer.parseInt(parts[1]) : 130;
                List<AccessibilityNodeInfo> list =
                        clickables(getUiAutomation().getRootInActiveWindow(), leftmax);
                sb.append("OK clickables=").append(list.size());
                for (int i = 0; i < list.size(); i++) {
                    sb.append('\n').append(i + 1).append(' ').append(desc(list.get(i)));
                }
                break;
            }

            case "scan": {
                // On-device vision: screenshot + candidate search happen here,
                // only compact numbers go back.  Classification (stop vs spawn)
                // is done host-side so thresholds can be tuned without a rebuild.
                long t0 = System.currentTimeMillis();
                Bitmap shot = getUiAutomation().takeScreenshot();
                if (shot == null) {
                    sb.append("ERR noshot");
                    break;
                }
                int W = shot.getWidth(), H = shot.getHeight();
                Bitmap small = Bitmap.createScaledBitmap(shot, Math.max(1, W / 4),
                        Math.max(1, H / 4), false);
                int sw = small.getWidth(), sh = small.getHeight();
                int[] px = new int[sw * sh];
                small.getPixels(px, 0, sw, 0, 0, sw, sh);
                List<int[]> objs = new ArrayList<>();   // {x, y, var, orange100, violet100}
                scanMap(px, sw, sh, objs);
                sb.append("OK scan ms=").append(System.currentTimeMillis() - t0)
                  .append(" w=").append(W).append(" h=").append(H)
                  .append(" objects=").append(objs.size());
                for (int[] o : objs) {
                    sb.append("\nobj ").append(o[0] * 4).append(' ').append(o[1] * 4)
                      .append(' ').append(o[2])
                      .append(' ').append(o[3]).append(' ').append(o[4])
                      .append(' ').append(o[5]).append(' ').append(o[6]);
                }
                small.recycle();
                shot.recycle();
                break;
            }

            case "catchseq": {
                // Throw, wait for the result, press OK — ONE round trip.
                // The physical animation cannot be skipped, but every adb
                // round trip inside the sequence can be: ~6.4 s -> ~3 s.
                int maxThrows = parts.length > 1 ? Integer.parseInt(parts[1]) : 3;
                long t0 = System.currentTimeMillis();
                int throwsDone = 0;
                boolean ended = false, mapBack = false;
                for (int i = 0; i < maxThrows; i++) {
                    if (!isEncounter()) break;
                    injectSwipe(540, 1900, 540, 800, 120);
                    throwsDone++;
                    if (waitEncounterGone(15000, 8, 60)) {
                        ended = true;
                        break;
                    }
                }
                if (ended) {
                    mapBack = pressOkAndWait(6000);
                }
                sb.append("OK catchseq throws=").append(throwsDone)
                  .append(" ended=").append(ended ? 1 : 0)
                  .append(" map=").append(mapBack ? 1 : 0)
                  .append(" warm=").append(warmNow())
                  .append(" ms=").append(System.currentTimeMillis() - t0);
                break;
            }

            case "tapwait": {
                // Tap, then decide — all inside ONE adb round trip.
                //
                // The adb round trip itself costs ~220 ms, so the old
                // tap -> sleep(2000) -> dump -> probe sequence spent ~2.8 s per
                // tap.  Here the phone does the waiting: it polls the node tree
                // and the screen probe every ~100 ms and stops the moment
                // something changes, then returns texts + warm together.
                float x = Float.parseFloat(parts[1]);
                float y = Float.parseFloat(parts[2]);
                int settle = parts.length > 3 ? Integer.parseInt(parts[3]) : 1200;
                // "nowarm" keeps the whole wait on the cheap node-tree path.
                // On event maps the map itself is warm, so the pixel probe
                // reports an overlay on every frame and must be switched off.
                boolean useWarm = !(parts.length > 4 && parts[4].equals("nowarm"));
                String before = sig();
                long t0 = System.currentTimeMillis();
                injectTap(x, y);
                String after = before;
                int warm = 0;
                boolean changed = false;
                while (System.currentTimeMillis() - t0 < settle) {
                    sleep(70);
                    after = sig();
                    if (!after.equals(before)) {
                        changed = true;
                        break;
                    }
                    // A Unity overlay (PokéStop disc, gym sheet) changes no
                    // nodes at all, so the pixels are checked as well.
                    if (useWarm) {
                        int w = warmNow();
                        if (w != Integer.MIN_VALUE && w > WARM_OVERLAY_X10) {
                            warm = w;
                            changed = true;
                            break;
                        }
                    }
                }
                if (warm == 0 && useWarm) warm = warmNow();
                sb.append("OK tapwait ms=").append(System.currentTimeMillis() - t0)
                  .append(" changed=").append(changed ? 1 : 0)
                  .append(" warm=").append(warm)
                  .append(" texts=").append(after);
                break;
            }

            case "probe": {
                // Cheap screen-type probe: a full-screen Unity overlay (PokéStop
                // photo disc, gym sheet, catch screen) has a warm, high-saturation
                // centre, while the map is a flat blue-grey.  Costs one screenshot
                // at 1/4 scale and ~10 ms of maths.
                Bitmap shot = getUiAutomation().takeScreenshot();
                if (shot == null) {
                    sb.append("ERR noshot");
                    break;
                }
                int W = shot.getWidth(), H = shot.getHeight();
                Bitmap small = Bitmap.createScaledBitmap(shot, Math.max(1, W / 4),
                        Math.max(1, H / 4), false);
                int sw = small.getWidth(), sh = small.getHeight();
                int[] px = new int[sw * sh];
                small.getPixels(px, 0, sw, 0, 0, sw, sh);
                int x0 = sw / 7, x1 = sw - sw / 7, y0 = sh / 4, y1 = sh - sh / 4;
                double sr = 0, sb2 = 0, sl = 0, ss = 0, ss2 = 0;
                int n = 0;
                for (int y = y0; y < y1; y++) {
                    for (int x = x0; x < x1; x++) {
                        int c = px[y * sw + x];
                        int r = (c >> 16) & 0xFF, g = (c >> 8) & 0xFF, b = c & 0xFF;
                        sr += r - b;
                        sb2 += 0;
                        sl += 0.299 * r + 0.587 * g + 0.114 * b;
                        int mx = Math.max(r, Math.max(g, b));
                        int mn = Math.min(r, Math.min(g, b));
                        ss += mx - mn;
                        ss2 += (mx - mn) * (mx - mn);
                        n++;
                    }
                }
                double warm = sr / n;
                double sat = ss / n;
                double satSd = Math.sqrt(Math.max(0, ss2 / n - sat * sat));
                sb.append("OK probe warm=").append(Math.round(warm * 10))
                  .append(" sat=").append(Math.round(sat * 10))
                  .append(" satsd=").append(Math.round(satSd * 10))
                  .append(" lum=").append(Math.round(sl / n * 10));
                small.recycle();
                shot.recycle();
                break;
            }

            case "click": {
                float x = Float.parseFloat(parts[1]);
                float y = Float.parseFloat(parts[2]);
                injectTap(x, y);
                sb.append("OK click ").append(x).append(' ').append(y);
                break;
            }

            case "double": {
                // Two taps inside one command: the file-protocol round trip
                // (~100 ms) would otherwise make the pair too slow to count
                // as a double tap.
                float x = Float.parseFloat(parts[1]);
                float y = Float.parseFloat(parts[2]);
                long gap = parts.length > 3 ? Long.parseLong(parts[3]) : 55;
                injectTap(x, y);
                sleep(gap);
                injectTap(x, y);
                sb.append("OK double ").append(x).append(' ').append(y)
                  .append(" gap=").append(gap);
                break;
            }

            case "swipe": {
                float x1 = Float.parseFloat(parts[1]);
                float y1 = Float.parseFloat(parts[2]);
                float x2 = Float.parseFloat(parts[3]);
                float y2 = Float.parseFloat(parts[4]);
                long dur = Long.parseLong(parts[5]);
                injectSwipe(x1, y1, x2, y2, dur);
                sb.append("OK swipe ");
                break;
            }

            default:
                sb.append("ERR unknown ").append(cmd);
        }
        return sb.toString();
    }

    /** Everything after the first token: labels may contain spaces. */
    private static String argAfter(String line) {
        int i = line.indexOf(' ');
        return i < 0 ? "" : line.substring(i + 1).trim();
    }

    private void injectTap(float x, float y) {
        long t = System.currentTimeMillis();
        MotionEvent d = MotionEvent.obtain(t, t, MotionEvent.ACTION_DOWN, x, y, 0);
        getUiAutomation().injectInputEvent(d, true);
        d.recycle();
        MotionEvent u = MotionEvent.obtain(t, t + 30, MotionEvent.ACTION_UP, x, y, 0);
        getUiAutomation().injectInputEvent(u, true);
        u.recycle();
    }

    private void injectSwipe(float x1, float y1, float x2, float y2, long dur) {
        long t = System.currentTimeMillis();
        int steps = 14;
        MotionEvent d = MotionEvent.obtain(t, t, MotionEvent.ACTION_DOWN, x1, y1, 0);
        getUiAutomation().injectInputEvent(d, true);
        d.recycle();
        for (int i = 1; i <= steps; i++) {
            float f = i / (float) steps;
            long et = t + dur * i / steps;
            MotionEvent m = MotionEvent.obtain(t, et, MotionEvent.ACTION_MOVE,
                    x1 + (x2 - x1) * f, y1 + (y2 - y1) * f, 0);
            getUiAutomation().injectInputEvent(m, true);
            m.recycle();
            sleep((int) Math.max(1, dur / steps));
        }
        MotionEvent u = MotionEvent.obtain(t, t + dur, MotionEvent.ACTION_UP, x2, y2, 0);
        getUiAutomation().injectInputEvent(u, true);
        u.recycle();
    }

    private void walk(AccessibilityNodeInfo n, List<AccessibilityNodeInfo> out) {
        if (n == null) return;
        out.add(n);
        for (int i = 0; i < n.getChildCount(); i++) {
            walk(n.getChild(i), out);
        }
    }

    private String desc(AccessibilityNodeInfo n) {
        StringBuilder sb = new StringBuilder();
        sb.append(n.getClassName() == null ? "" : n.getClassName().toString());
        sb.append('|');
        sb.append(n.getText() == null ? "" : n.getText().toString().replace('\n', ' '));
        sb.append('|');
        sb.append(n.getContentDescription() == null ? "" : n.getContentDescription().toString().replace('\n', ' '));
        android.graphics.Rect b = new android.graphics.Rect();
        n.getBoundsInScreen(b);
        sb.append('|').append(b.left).append(',').append(b.top)
          .append(',').append(b.right).append(',').append(b.bottom);
        sb.append('|');
        if (n.isClickable()) sb.append('C');
        if (n.isEnabled()) sb.append('E');
        if (n.isCheckable()) sb.append('K');
        if (n.isChecked()) sb.append('X');
        return sb.toString();
    }

    // ------------------------------------------------------------ on-device CV
    private static final int[] DX4 = {-1, 1, 0, 0};
    private static final int[] DY4 = {0, 0, -1, 1};

    /**
     * Find world objects at 1/4 scale.
     *
     * Candidates are local-variance peaks inside the avatar's interaction
     * radius (a wild spawn only renders large near the player, while gyms,
     * balloons and HUD icons are far away or pinned to the screen edge).
     * Each candidate is returned with the orange and violet ratio around it so
     * the host can classify PokéStop (free / spun) vs wild spawn.
     *
     * @return list of {x, y, variance, orange*100, violet*100}
     */
    private void scanMap(int[] px, int w, int h, List<int[]> objs) {
        int n = w * h;
        double[] lum = new double[n];
        int[] mask = new int[n];                  // 0 none, 1 orange, 2 violet
        for (int i = 0; i < n; i++) {
            int c = px[i];
            int r = (c >> 16) & 0xFF, g = (c >> 8) & 0xFF, b = c & 0xFF;
            lum[i] = 0.299 * r + 0.587 * g + 0.114 * b;
            if (r > 150 && r - b > 90 && g > 60 && g < 200) mask[i] = 1;
            else if (b > 110 && b - r > 45 && b - g > 10) mask[i] = 2;
        }

        int stride = w + 1;
        double[] ii = new double[stride * (h + 1)];
        double[] ii2 = new double[stride * (h + 1)];
        double[] iio = new double[stride * (h + 1)];
        double[] iiv = new double[stride * (h + 1)];
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                int i = y * w + x;
                int k = (y + 1) * stride + (x + 1);
                double v = lum[i];
                double o = mask[i] == 1 ? 1 : 0;
                double vi = mask[i] == 2 ? 1 : 0;
                ii[k] = v + ii[k - 1] + ii[k - stride] - ii[k - stride - 1];
                ii2[k] = v * v + ii2[k - 1] + ii2[k - stride] - ii2[k - stride - 1];
                iio[k] = o + iio[k - 1] + iio[k - stride] - iio[k - stride - 1];
                iiv[k] = vi + iiv[k - 1] + iiv[k - stride] - iiv[k - stride - 1];
            }
        }

        final int K = 7;
        final double AX = w * 0.5, AY = h * 0.67;   // avatar: centre, slightly low
        final double RIN = 22, ROUT = Math.min(w, h) * 0.30;
        List<int[]> cand = new ArrayList<>();
        for (int y = K; y + K < h; y += 2) {
            for (int x = K; x + K < w; x += 2) {
                double dx = x - AX, dy = y - AY;
                double d = Math.sqrt(dx * dx + dy * dy);
                if (d < RIN || d > ROUT) continue;
                double s = boxSum(ii, stride, x - K / 2, y - K / 2, K);
                double s2 = boxSum(ii2, stride, x - K / 2, y - K / 2, K);
                int cnt = K * K;
                double mean = s / cnt;
                double var = s2 / cnt - mean * mean;
                if (var < 700) continue;
                cand.add(new int[]{(int) var, x, y});
            }
        }
        cand.sort((a, b) -> Integer.compare(b[0], a[0]));

        final int R = 5;                            // colour box radius (1/4 scale)
        boolean[] pale = new boolean[n];
        for (int i = 0; i < n; i++) {
            int c = px[i];
            int r = (c >> 16) & 0xFF, g = (c >> 8) & 0xFF, b = c & 0xFF;
            int mx = Math.max(r, Math.max(g, b));
            int mn = Math.min(r, Math.min(g, b));
            pale[i] = mx > 150 && (mx - mn) < 55;
        }
        for (int[] c : cand) {
            boolean keep = true;
            for (int[] k : objs) {
                int ddx = c[1] - k[0], ddy = c[2] - k[1];
                if (ddx * ddx + ddy * ddy < 20 * 20) { keep = false; break; }
            }
            if (!keep) continue;
            double bestO = 0, bestV = 0;
            int[][] offs = {{0, 0}, {0, -8}, {0, 8}, {-8, 0}, {8, 0}};
            for (int[] off : offs) {
                int bx = c[1] + off[0] - R, by = c[2] + off[1] - R;
                int bw = 2 * R + 1;
                if (bx < 0 || by < 0 || bx + bw >= w || by + bw >= h) continue;
                double o = boxSum(iio, stride, bx, by, bw) / (bw * bw);
                double vi = boxSum(iiv, stride, bx, by, bw) / (bw * bw);
                if (o > bestO) bestO = o;
                if (vi > bestV) bestV = vi;
            }
            // shape: bbox of the orange|violet mask around the candidate.
            // PokéStop towers are tall (h > w); Pokémon sprites are not.
            int W2 = 22, minx = w, maxx = -1, miny = h, maxy = -1;
            for (int y = Math.max(0, c[2] - W2); y < Math.min(h, c[2] + W2); y++) {
                for (int x = Math.max(0, c[1] - W2); x < Math.min(w, c[1] + W2); x++) {
                    if (mask[y * w + x] == 0) continue;
                    if (x < minx) minx = x;
                    if (x > maxx) maxx = x;
                    if (y < miny) miny = y;
                    if (y > maxy) maxy = y;
                }
            }
            int hw10 = 10;                          // default 1.0
            if (maxx >= minx && maxy >= miny) {
                int bw = maxx - minx + 1, bh = maxy - miny + 1;
                if (bw > 0) hw10 = (bh * 10) / bw;
            }
            objs.add(new int[]{c[1], c[2], c[0], (int) (bestO * 100),
                    (int) (bestV * 100), hw10, ringScore(pale, w, h, c[1], c[2])});
            if (objs.size() >= 12) break;
        }
    }

    /**
     * Fraction of sample points on a pale ellipse around (x, y), 0..100.
     *
     * Every PokéStop stands inside a white ring on the ground; wild spawns have
     * only a dark shadow.  The ring is searched over a small family of centres
     * (it sits below the tower) and radii, so it works at any zoom level.
     */
    private static int ringScore(boolean[] pale, int w, int h, int x, int y) {
        final int[] DYS = {-2, 2, 7, 12, 17};
        final int[] RXS = {12, 17, 22, 27, 32, 37};
        final int ANGLES = 36;
        int best = 0;
        for (int dy : DYS) {
            int cy = y + dy;
            for (int rx : RXS) {
                double ry = rx * 0.42;
                if (cy + ry >= h || cy - ry < 0 || x + rx >= w || x - rx < 0) continue;
                int hit = 0;
                for (int i = 0; i < ANGLES; i++) {
                    double t = 2 * Math.PI * i / ANGLES;
                    int px = (int) (x + rx * Math.cos(t));
                    int py = (int) (cy + ry * Math.sin(t));
                    if (px >= 0 && py >= 0 && px < w && py < h && pale[py * w + px]) hit++;
                }
                int pct = hit * 100 / ANGLES;
                if (pct > best) best = pct;
            }
        }
        return best;
    }

    private static double boxSum(double[] ii, int stride, int x0, int y0, int k) {
        int a = y0 * stride + x0;
        int b = y0 * stride + (x0 + k);
        int c = (y0 + k) * stride + x0;
        int d = (y0 + k) * stride + (x0 + k);
        return ii[d] - ii[b] - ii[c] + ii[a];
    }

    // ---------------------------------------------------------- cheap probes
    /** mean(R-B)*10 above this means a full-screen Unity overlay, not the map. */
    private static final int WARM_OVERLAY_X10 = -120;

    /** True while the berry row is on screen — the only reliable encounter marker. */
    private boolean isEncounter() {
        String s = sig();
        return s.contains("蔓莓果") || s.contains("蕉香果") || s.contains("凰梨果");
    }

    /**
     * Wait until the berry row has been gone for `stable` consecutive reads.
     *
     * A single miss is not evidence: the row disappears for ~1 s during the
     * throw animation.  Polling on-device (60 ms) avoids the ~220 ms adb round
     * trip that the host-side version paid for on every read.
     */
    private boolean waitEncounterGone(int timeoutMs, int stable, int pollMs) {
        long t0 = System.currentTimeMillis();
        int miss = 0;
        while (System.currentTimeMillis() - t0 < timeoutMs) {
            if (isEncounter()) {
                miss = 0;
            } else if (++miss >= stable) {
                return true;
            }
            sleep(pollMs);
        }
        return false;
    }

    /** Press the result card's OK (accessibility first), then wait for the map. */
    private boolean pressOkAndWait(int timeoutMs) {
        String[] labels = {"OK", "確定", "好"};
        for (String label : labels) {
            AccessibilityNodeInfo hit = findText(
                    getUiAutomation().getRootInActiveWindow(), label);
            if (hit != null) {
                hit.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                break;
            }
        }
        long t0 = System.currentTimeMillis();
        boolean tapped = false;
        int miss = 0;
        while (System.currentTimeMillis() - t0 < timeoutMs) {
            sleep(120);
            // The berry row is the authoritative encounter marker.  Waiting
            // for it to disappear works on every map skin, unlike the warmth
            // probe (event maps are warm even on the bare map).
            if (isEncounter()) {
                miss = 0;
            } else if (++miss >= 6) {
                return true;               // back on the map
            }
            if (!tapped && System.currentTimeMillis() - t0 > 1200) {
                injectTap(539, 1580);      // the result card's OK button
                tapped = true;
            }
        }
        return false;
    }

    /** Distinct texts of every window, joined by \\u0001.  ~25 ms. */
    private String sig() {
        java.util.LinkedHashSet<String> ts = new java.util.LinkedHashSet<>();
        try {
            for (AccessibilityWindowInfo w : getUiAutomation().getWindows()) {
                collectTexts(w.getRoot(), ts);
            }
            collectTexts(getUiAutomation().getRootInActiveWindow(), ts);
        } catch (Throwable e) {
            // fall through with whatever we have
        }
        StringBuilder b = new StringBuilder();
        for (String t : ts) {
            if (t == null || t.isEmpty()) continue;
            if (b.length() > 0) b.append('\u0001');
            b.append(t.replace('\u0001', ' ').replace('\n', ' '));
            if (b.length() > 1200) break;
        }
        return b.toString();
    }

    private static void collectTexts(AccessibilityNodeInfo n,
                                     java.util.Set<String> out) {
        if (n == null) return;
        CharSequence t = n.getText();
        if (t != null) out.add(t.toString());
        CharSequence d = n.getContentDescription();
        if (d != null) out.add(d.toString());
        for (int i = 0; i < n.getChildCount(); i++) {
            collectTexts(n.getChild(i), out);
        }
    }

    /**
     * Mean(R-B)*10 over the central area of a 1/4-scale screenshot.
     *
     * The map is strongly blue-grey (about -250), while any Unity overlay is
     * warm and near 0.  Returns Integer.MIN_VALUE if no screenshot is available.
     */
    private int warmNow() {
        try {
            Bitmap shot = getUiAutomation().takeScreenshot();
            if (shot == null) return Integer.MIN_VALUE;
            int W = shot.getWidth(), H = shot.getHeight();
            Bitmap small = Bitmap.createScaledBitmap(shot, Math.max(1, W / 4),
                    Math.max(1, H / 4), false);
            int sw = small.getWidth(), sh = small.getHeight();
            int[] px = new int[sw * sh];
            small.getPixels(px, 0, sw, 0, 0, sw, sh);
            int x0 = sw / 7, x1 = sw - sw / 7, y0 = sh / 4, y1 = sh - sh / 4;
            long sum = 0;
            int n = 0;
            for (int y = y0; y < y1; y++) {
                int row = y * sw;
                for (int x = x0; x < x1; x++) {
                    int c = px[row + x];
                    sum += ((c >> 16) & 0xFF) - (c & 0xFF);
                    n++;
                }
            }
            small.recycle();
            shot.recycle();
            return n == 0 ? Integer.MIN_VALUE : (int) (sum * 10 / n);
        } catch (Throwable e) {
            return Integer.MIN_VALUE;
        }
    }

    /** Clickable nodes inside the left strip, ordered top-to-bottom. */    private List<AccessibilityNodeInfo> clickables(AccessibilityNodeInfo root, int leftmax) {
        List<AccessibilityNodeInfo> out = new ArrayList<>();
        if (root == null) return out;
        List<AccessibilityNodeInfo> stack = new ArrayList<>();
        stack.add(root);
        while (!stack.isEmpty()) {
            AccessibilityNodeInfo cur = stack.remove(stack.size() - 1);
            android.graphics.Rect b = new android.graphics.Rect();
            cur.getBoundsInScreen(b);
            if (cur.isClickable() && b.left <= leftmax
                    && b.width() > 0 && b.height() > 0 && b.height() < 400) {
                out.add(cur);
            }
            for (int i = 0; i < cur.getChildCount(); i++) stack.add(cur.getChild(i));
        }
        out.sort((x, y) -> {
            android.graphics.Rect rx = new android.graphics.Rect();
            android.graphics.Rect ry = new android.graphics.Rect();
            x.getBoundsInScreen(rx);
            y.getBoundsInScreen(ry);
            if (rx.top != ry.top) return Integer.compare(rx.top, ry.top);
            return Integer.compare(rx.left, ry.left);
        });
        return out;
    }

    private AccessibilityNodeInfo findCheckable(AccessibilityNodeInfo n) {
        if (n == null) return null;
        List<AccessibilityNodeInfo> stack = new ArrayList<>();
        stack.add(n);
        while (!stack.isEmpty()) {
            AccessibilityNodeInfo cur = stack.remove(stack.size() - 1);
            if (cur.isCheckable()) return cur;
            for (int i = 0; i < cur.getChildCount(); i++) {
                stack.add(cur.getChild(i));
            }
        }
        return null;
    }

    private AccessibilityNodeInfo findCheckableUp(AccessibilityNodeInfo n) {
        AccessibilityNodeInfo cur = n;
        for (int depth = 0; depth < 6 && cur != null; depth++) {
            cur = cur.getParent();
            if (cur == null) return null;
            if (cur.isCheckable()) return cur;
            AccessibilityNodeInfo deep = findCheckable(cur);
            if (deep != null) return deep;
        }
        return null;
    }

    private AccessibilityNodeInfo findText(AccessibilityNodeInfo n, String want) {
        // Exact label first (so "快速狙擊 I" never matches "快速狙擊 II"),
        // then fall back to substring.
        AccessibilityNodeInfo exact = findTextPass(n, want, true);
        return exact != null ? exact : findTextPass(n, want, false);
    }

    private AccessibilityNodeInfo findTextPass(AccessibilityNodeInfo n, String want, boolean exact) {
        if (n == null) return null;
        List<AccessibilityNodeInfo> stack = new ArrayList<>();
        stack.add(n);
        while (!stack.isEmpty()) {
            AccessibilityNodeInfo cur = stack.remove(stack.size() - 1);
            CharSequence t = cur.getText();
            CharSequence d = cur.getContentDescription();
            String ts = t == null ? "" : t.toString();
            String ds = d == null ? "" : d.toString();
            boolean hit = exact ? (ts.equals(want) || ds.equals(want))
                                : (ts.contains(want) || ds.contains(want));
            if (hit && !(ts.isEmpty() && ds.isEmpty())) {
                return cur;
            }
            for (int i = 0; i < cur.getChildCount(); i++) {
                stack.add(cur.getChild(i));
            }
        }
        return null;
    }

    private static void sleep(long ms) {
        try { Thread.sleep(ms); } catch (InterruptedException ignored) { }
    }

    private static String read(File f) {
        try (BufferedReader r = new BufferedReader(new FileReader(f))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) sb.append(line);
            return sb.toString();
        } catch (Exception e) {
            return null;
        }
    }

    private static void write(File f, String content) {
        try (PrintWriter w = new PrintWriter(f, "UTF-8")) {
            w.write(content);
        } catch (Exception e) {
            Log.e(TAG, "write", e);
        }
    }
}

