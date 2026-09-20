from flask import Flask, jsonify, render_template_string, request

import database
import firebase_service


app = Flask(__name__)


HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rickshaw Information</title>
<style>
body {
    margin: 0;
    padding: 20px;
    background: #0f172a;
    color: white;
    font-family: Arial, sans-serif;
}
.container { max-width: 620px; margin: auto; }
.card {
    background: #1e293b;
    border-radius: 18px;
    padding: 25px;
    box-shadow: 0 10px 30px rgba(0,0,0,.3);
}
.header { text-align: center; margin-bottom: 20px; }
.title { font-size: 28px; font-weight: bold; }
.subtitle { color: #94a3b8; margin-top: 5px; }
.profile { text-align: center; margin: 20px 0; }
.profile img {
    width: 150px;
    height: 150px;
    border-radius: 50%;
    object-fit: cover;
    border: 4px solid #3b82f6;
}
.row {
    background: #0f172a;
    margin: 10px 0;
    padding: 14px;
    border-radius: 10px;
}
.label {
    color: #94a3b8;
    font-size: 12px;
    text-transform: uppercase;
}
.value { font-size: 18px; margin-top: 4px; font-weight: bold; }
.active { color: #22c55e; }
.inactive { color: #f59e0b; }
.error { color: #f87171; text-align: center; padding: 25px; }
.sync { color: #64748b; text-align: center; font-size: 12px; margin-top: 15px; }
</style>
</head>
<body>
<div class="container">
<div class="card">
    <div class="header">
        <div class="title">Rickshaw Information</div>
        <div class="subtitle">Verified Live Rickshaw Record</div>
    </div>

    <div id="content">
        <div class="sync">Loading live record...</div>
    </div>

    <div id="sync" class="sync"></div>
</div>
</div>

<script>
const token = {{ token|tojson }};

function esc(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function row(label, value, cssClass='') {
    return `
        <div class="row">
            <div class="label">${esc(label)}</div>
            <div class="value ${cssClass}">${esc(value || 'Not available')}</div>
        </div>`;
}

function render(data) {
    let html = '';

    html += row('Rickshaw', data.rickshaw_number);
    html += row('Registration Number', data.registration_number || 'Not available');
    html += row('Garage', data.garage_name || 'Not available');
    html += row('Garage Location', data.garage_location || 'Not available');
    html += row('Assigned Owner', data.owner_name || 'Not available');

    if (data.status === 'ACTIVE') {
        if (data.puller_photo) {
            html += `<div class="profile"><img alt="Puller photo" src="${data.puller_photo}"></div>`;
        }
        html += row('Current Rickshaw Puller', data.puller_name || 'Not available');
        html += row('Puller ID', data.puller_code || 'Not available');
        html += row('Status', '● CURRENTLY ASSIGNED', 'active');
        html += row('Started', data.started_at || 'Not available');
    } else {
        html += row('Current Puller', 'No puller currently assigned', 'inactive');
        html += row('Status', '● INSIDE GARAGE', 'inactive');
    }

    document.getElementById('content').innerHTML = html;
    document.getElementById('sync').textContent =
        'Live data • Last checked ' + new Date().toLocaleTimeString();
}

async function refresh() {
    try {
        const response = await fetch('/api/r/' + encodeURIComponent(token), {
            cache: 'no-store'
        });
        if (!response.ok) {
            throw new Error('Rickshaw record not found');
        }
        const data = await response.json();
        render(data);
    } catch (err) {
        document.getElementById('content').innerHTML =
            '<div class="error">' + esc(err.message) + '</div>';
    }
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


def _firebase_public_record(token):
    try:
        return firebase_service.get_public_rickshaw(token)
    except Exception as exc:
        print("[QR FIREBASE READ ERROR]", repr(exc))
        return None


def _local_fallback_record(token):
    """
    Local fallback only. In normal multi-device operation the public Firebase
    record is used because a phone may start a session while this PC is off.
    """
    try:
        rickshaw = database.get_rickshaw_by_token(token)
        if not rickshaw:
            return None

        session = database.get_active_session(rickshaw["id"])
        data = {
            "rickshaw_id": rickshaw["id"],
            "rickshaw_number": rickshaw.get("rickshaw_number") or "",
            "registration_number": rickshaw.get("registration_number") or "",
            "garage_name": rickshaw.get("final_garage_name") or rickshaw.get("garage_name") or "",
            "garage_location": rickshaw.get("final_garage_location") or rickshaw.get("garage_location") or "",
            "owner_name": rickshaw.get("owner_name") or "",
            "status": "ACTIVE" if session else "IDLE",
            "cloud_session_id": session.get("cloud_id") if session else None,
            "puller_id": session.get("puller_id") if session else None,
            "puller_name": session.get("puller_name") if session else "",
            "puller_code": session.get("puller_code") if session else "",
            "puller_photo": "",
            "started_at": session.get("started_at") if session else None,
            "ended_at": None,
        }

        if session:
            photo = session.get("puller_photo_url") or session.get("puller_photo") or ""
            data["puller_photo"] = firebase_service.photo_to_base64(photo)

        return data
    except Exception as exc:
        print("[QR LOCAL FALLBACK ERROR]", repr(exc))
        return None


def get_live_record(token):
    return _firebase_public_record(token) or _local_fallback_record(token)


@app.route('/api/r/<token>')
def rickshaw_api(token):
    record = get_live_record(token)
    if not record:
        return jsonify({"error": "Rickshaw not found"}), 404
    return jsonify(record)


@app.route('/r/<token>')
def rickshaw_page(token):
    return render_template_string(HTML, token=token)


@app.route('/rickshaw.html')
def hosted_style_route():
    token = str(request.args.get('token') or '').strip()
    if not token:
        return '<h1>Missing token</h1>', 400
    return render_template_string(HTML, token=token)


@app.route('/')
def home():
    return (
        '<h1>RFID Rickshaw QR Server</h1>'
        '<p>Firebase-backed live server is running.</p>'
    )


def run_server():
    database.init_database()
    firebase_service.initialize_firebase()
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        use_reloader=False
    )


if __name__ == '__main__':
    run_server()
