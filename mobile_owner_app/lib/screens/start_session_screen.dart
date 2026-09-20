import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/rfid_utils.dart';
import '../services/rtdb_service.dart';
import '../widgets/puller_photo.dart';
import '../widgets/rfid_scan_field.dart';

enum _ScanStage { master, slave, ready }

class StartSessionScreen extends StatefulWidget {
  const StartSessionScreen({
    super.key,
    required this.service,
    required this.owner,
    required this.rickshaw,
  });

  final RtdbService service;
  final OwnerProfile owner;
  final Rickshaw rickshaw;

  @override
  State<StartSessionScreen> createState() => _StartSessionScreenState();
}

class _StartSessionScreenState extends State<StartSessionScreen> {
  _ScanStage _stage = _ScanStage.master;
  bool _busy = false;
  String _masterUid = '';
  String _slaveUid = '';
  Puller? _puller;
  String _message = 'Scan the owner Master RFID card.';
  bool _error = false;

  Future<void> _scanMaster(String raw) async {
    if (_busy || _stage != _ScanStage.master) return;
    final uid = normalizeUid(raw);
    setState(() {
      _busy = true;
      _error = false;
      _message = 'Verifying Master RFID...';
    });

    final valid = await widget.service.verifyMasterUid(
      uid: uid,
      ownerId: widget.owner.id,
    );

    if (!mounted) return;
    if (!valid) {
      setState(() {
        _busy = false;
        _error = true;
        _message = 'Master RFID is not authorized for this owner.';
      });
      return;
    }

    setState(() {
      _busy = false;
      _masterUid = uid;
      _stage = _ScanStage.slave;
      _message = 'Master verified. Now scan the Puller Slave RFID card.';
    });
  }

  Future<void> _scanSlave(String raw) async {
    if (_busy || _stage != _ScanStage.slave) return;
    final uid = normalizeUid(raw);
    setState(() {
      _busy = true;
      _error = false;
      _message = 'Verifying Puller RFID...';
    });

    final puller = await widget.service.getPullerBySlaveUid(uid);
    if (!mounted) return;

    if (puller == null) {
      setState(() {
        _busy = false;
        _error = true;
        _message = 'This Slave RFID is not assigned to an active puller.';
      });
      return;
    }

    setState(() {
      _busy = false;
      _slaveUid = uid;
      _puller = puller;
      _stage = _ScanStage.ready;
      _message = 'Puller verified. Confirm to activate this rickshaw session.';
    });
  }

  Future<void> _activate() async {
    final puller = _puller;
    if (_busy || puller == null) return;

    setState(() {
      _busy = true;
      _error = false;
      _message = 'Creating active session...';
    });

    final result = await widget.service.startSession(
      rickshaw: widget.rickshaw,
      owner: widget.owner,
      puller: puller,
      masterUid: _masterUid,
      slaveUid: _slaveUid,
    );

    if (!mounted) return;
    if (result.started) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message)),
      );
      Navigator.of(context).pop(true);
      return;
    }

    setState(() {
      _busy = false;
      _error = true;
      _message = result.message;
    });
  }

  void _restart() {
    setState(() {
      _stage = _ScanStage.master;
      _busy = false;
      _masterUid = '';
      _slaveUid = '';
      _puller = null;
      _error = false;
      _message = 'Scan the owner Master RFID card.';
    });
  }

  @override
  Widget build(BuildContext context) {
    final puller = _puller;
    return Scaffold(
      appBar: AppBar(title: const Text('Start Session')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Card(
            child: ListTile(
              leading: const CircleAvatar(child: Icon(Icons.electric_rickshaw)),
              title: Text(
                widget.rickshaw.number,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              subtitle: Text(
                widget.rickshaw.registrationNumber.isEmpty
                    ? 'No registration number'
                    : widget.rickshaw.registrationNumber,
              ),
              trailing: Text(widget.owner.name),
            ),
          ),
          const SizedBox(height: 16),
          _StepTile(
            number: 1,
            title: 'Master RFID',
            subtitle: _masterUid.isEmpty ? 'Waiting for owner card' : 'Verified',
            complete: _masterUid.isNotEmpty,
            active: _stage == _ScanStage.master,
          ),
          _StepTile(
            number: 2,
            title: 'Slave RFID',
            subtitle: _slaveUid.isEmpty ? 'Waiting for puller card' : 'Verified',
            complete: _slaveUid.isNotEmpty,
            active: _stage == _ScanStage.slave,
          ),
          _StepTile(
            number: 3,
            title: 'Activate',
            subtitle: puller == null ? 'Verify both RFID cards first' : puller.name,
            complete: false,
            active: _stage == _ScanStage.ready,
          ),
          const SizedBox(height: 16),
          AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              color: _error
                  ? Theme.of(context).colorScheme.errorContainer
                  : Theme.of(context).colorScheme.primaryContainer,
            ),
            child: Row(
              children: [
                Icon(_error ? Icons.error_outline : Icons.info_outline),
                const SizedBox(width: 10),
                Expanded(child: Text(_message)),
                if (_busy)
                  const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          if (_stage == _ScanStage.master)
            RfidScanField(
              key: const ValueKey('master'),
              label: 'Master RFID Scanner',
              enabled: !_busy,
              onScan: _scanMaster,
            ),
          if (_stage == _ScanStage.slave)
            RfidScanField(
              key: const ValueKey('slave'),
              label: 'Slave RFID Scanner',
              enabled: !_busy,
              onScan: _scanSlave,
            ),
          if (puller != null) ...[
            const SizedBox(height: 18),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    PullerPhoto(dataUrl: puller.photo, size: 82),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            puller.name,
                            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                  fontWeight: FontWeight.w800,
                                ),
                          ),
                          const SizedBox(height: 6),
                          Text('Puller ID: ${puller.pullerCode.isEmpty ? '---' : puller.pullerCode}'),
                          Text('Phone: ${puller.phone.isEmpty ? '---' : puller.phone}'),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _busy ? null : _activate,
              icon: const Icon(Icons.play_arrow),
              label: const Text('ACTIVATE SESSION'),
            ),
            OutlinedButton(
              onPressed: _busy ? null : _restart,
              child: const Text('SCAN AGAIN'),
            ),
          ],
        ],
      ),
    );
  }
}

class _StepTile extends StatelessWidget {
  const _StepTile({
    required this.number,
    required this.title,
    required this.subtitle,
    required this.complete,
    required this.active,
  });

  final int number;
  final String title;
  final String subtitle;
  final bool complete;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final color = complete
        ? Colors.green
        : active
            ? Theme.of(context).colorScheme.primary
            : Colors.grey;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: CircleAvatar(
        backgroundColor: color,
        foregroundColor: Colors.white,
        child: complete ? const Icon(Icons.check) : Text('$number'),
      ),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(subtitle),
    );
  }
}
