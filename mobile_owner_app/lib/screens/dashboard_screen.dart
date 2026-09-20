import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/auth_service.dart';
import '../services/formatters.dart';
import '../services/rtdb_service.dart';
import '../widgets/puller_photo.dart';
import 'start_session_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    super.key,
    required this.auth,
    required this.service,
  });

  final AuthService auth;
  final RtdbService service;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late Future<(OwnerAccess, OwnerProfile)> _bootstrap;

  @override
  void initState() {
    super.initState();
    _bootstrap = _load();
  }

  Future<(OwnerAccess, OwnerProfile)> _load() async {
    final access = await widget.service.loadAccess();
    final owner = await widget.service.loadOwner(access.ownerId);
    return (access, owner);
  }

  void _retryBootstrap() {
    setState(() => _bootstrap = _load());
  }

  Future<void> _confirmEnd({
    required Rickshaw rickshaw,
    required OwnerProfile owner,
  }) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('End session?'),
        content: Text('End the active session for ${rickshaw.number}?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('END SESSION'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );
    try {
      final message = await widget.service.endSession(
        rickshaw: rickshaw,
        owner: owner,
      );
      if (mounted) {
        Navigator.of(context, rootNavigator: true).pop();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message)),
        );
      }
    } catch (error) {
      if (mounted) {
        Navigator.of(context, rootNavigator: true).pop();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Unable to end session: $error')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<(OwnerAccess, OwnerProfile)>(
      future: _bootstrap,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(body: Center(child: CircularProgressIndicator()));
        }
        if (snapshot.hasError || snapshot.data == null) {
          return Scaffold(
            appBar: AppBar(title: const Text('Rickshaw Owner')),
            body: Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.admin_panel_settings_outlined, size: 64),
                    const SizedBox(height: 16),
                    Text(
                      snapshot.error?.toString() ?? 'Unable to load owner access.',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 18),
                    FilledButton(
                      onPressed: _retryBootstrap,
                      child: const Text('RETRY'),
                    ),
                    TextButton(
                      onPressed: widget.auth.signOut,
                      child: const Text('SIGN OUT'),
                    ),
                  ],
                ),
              ),
            ),
          );
        }

        final (access, owner) = snapshot.data!;
        return _OwnerDashboard(
          access: access,
          owner: owner,
          auth: widget.auth,
          service: widget.service,
          onEnd: (rickshaw) => _confirmEnd(rickshaw: rickshaw, owner: owner),
        );
      },
    );
  }
}

class _OwnerDashboard extends StatelessWidget {
  const _OwnerDashboard({
    required this.access,
    required this.owner,
    required this.auth,
    required this.service,
    required this.onEnd,
  });

  final OwnerAccess access;
  final OwnerProfile owner;
  final AuthService auth;
  final RtdbService service;
  final ValueChanged<Rickshaw> onEnd;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Rickshaw Owner'),
        actions: [
          StreamBuilder<bool>(
            stream: service.connectionStream,
            initialData: false,
            builder: (context, snapshot) {
              final connected = snapshot.data == true;
              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Tooltip(
                  message: connected ? 'Firebase connected' : 'Reconnecting',
                  child: Icon(
                    connected ? Icons.cloud_done_outlined : Icons.cloud_off_outlined,
                    color: connected ? Colors.greenAccent : Colors.orangeAccent,
                  ),
                ),
              );
            },
          ),
          PopupMenuButton<String>(
            onSelected: (value) {
              if (value == 'logout') auth.signOut();
            },
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'logout', child: Text('Sign out')),
            ],
          ),
        ],
      ),
      body: StreamBuilder<List<Rickshaw>>(
        stream: service.watchRickshaws(access.ownerId),
        builder: (context, rickshawSnapshot) {
          if (rickshawSnapshot.hasError) {
            return _ErrorState(message: 'Unable to load rickshaws: ${rickshawSnapshot.error}');
          }
          if (!rickshawSnapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }

          final rickshaws = rickshawSnapshot.data!;
          final byId = {for (final r in rickshaws) r.id: r};

          return RefreshIndicator(
            onRefresh: () async {
              await service.loadOwner(access.ownerId);
            },
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              children: [
                _OwnerHeader(owner: owner, email: access.email),
                const SizedBox(height: 18),
                Text(
                  'Active Sessions',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 10),
                StreamBuilder<List<ActiveSession>>(
                  stream: service.watchOwnerActiveSessions(access.ownerId),
                  builder: (context, activeSnapshot) {
                    if (activeSnapshot.hasError) {
                      return _InlineNotice(
                        icon: Icons.sync_problem,
                        text: 'Active sessions are reconnecting...',
                      );
                    }
                    final sessions = activeSnapshot.data ?? const <ActiveSession>[];
                    if (sessions.isEmpty) {
                      return const _InlineNotice(
                        icon: Icons.check_circle_outline,
                        text: 'No active sessions.',
                      );
                    }
                    return Column(
                      children: sessions.map((session) {
                        final rickshaw = byId[session.rickshawId];
                        return Card(
                          child: ListTile(
                            leading: const CircleAvatar(
                              backgroundColor: Colors.green,
                              child: Icon(Icons.play_arrow, color: Colors.white),
                            ),
                            title: Text(
                              session.rickshawNumber.isEmpty
                                  ? (rickshaw?.number ?? 'Rickshaw ${session.rickshawId}')
                                  : session.rickshawNumber,
                              style: const TextStyle(fontWeight: FontWeight.w800),
                            ),
                            subtitle: Text(
                              '${session.pullerName}\nStarted: ${formatTimestamp(session.startedAt)}',
                            ),
                            isThreeLine: true,
                            trailing: rickshaw == null
                                ? null
                                : IconButton(
                                    tooltip: 'End session',
                                    onPressed: () => onEnd(rickshaw),
                                    icon: const Icon(Icons.stop_circle_outlined),
                                  ),
                          ),
                        );
                      }).toList(),
                    );
                  },
                ),
                const SizedBox(height: 22),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        'My Rickshaws',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w800,
                            ),
                      ),
                    ),
                    Text('${rickshaws.length} vehicle${rickshaws.length == 1 ? '' : 's'}'),
                  ],
                ),
                const SizedBox(height: 10),
                if (rickshaws.isEmpty)
                  const _InlineNotice(
                    icon: Icons.electric_rickshaw,
                    text: 'No rickshaws are assigned to this owner.',
                  )
                else
                  ...rickshaws.map(
                    (rickshaw) => _RickshawStatusCard(
                      rickshaw: rickshaw,
                      owner: owner,
                      service: service,
                      onEnd: () => onEnd(rickshaw),
                    ),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _OwnerHeader extends StatelessWidget {
  const _OwnerHeader({required this.owner, required this.email});

  final OwnerProfile owner;
  final String email;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const CircleAvatar(radius: 28, child: Icon(Icons.person, size: 30)),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    owner.name,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(owner.ownerCode.isEmpty ? 'Owner ID not set' : 'Owner ID: ${owner.ownerCode}'),
                  Text(owner.garageName.isEmpty ? 'Garage not set' : owner.garageName),
                  if (owner.garageLocation.isNotEmpty) Text(owner.garageLocation),
                  if (email.isNotEmpty) Text(email),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RickshawStatusCard extends StatelessWidget {
  const _RickshawStatusCard({
    required this.rickshaw,
    required this.owner,
    required this.service,
    required this.onEnd,
  });

  final Rickshaw rickshaw;
  final OwnerProfile owner;
  final RtdbService service;
  final VoidCallback onEnd;

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<LiveRickshaw>(
      stream: service.watchLiveRickshaw(rickshaw.id),
      initialData: LiveRickshaw.idle(),
      builder: (context, snapshot) {
        final live = snapshot.data ?? LiveRickshaw.idle();
        final active = live.isActive;

        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    CircleAvatar(
                      backgroundColor: active ? Colors.green : Colors.blueGrey,
                      child: const Icon(Icons.electric_rickshaw, color: Colors.white),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            rickshaw.number,
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w800,
                                ),
                          ),
                          Text(
                            rickshaw.registrationNumber.isEmpty
                                ? 'No registration number'
                                : rickshaw.registrationNumber,
                          ),
                        ],
                      ),
                    ),
                    Chip(
                      avatar: Icon(
                        active ? Icons.circle : Icons.home_outlined,
                        size: 14,
                        color: active ? Colors.green : null,
                      ),
                      label: Text(active ? 'ACTIVE' : 'IDLE'),
                    ),
                  ],
                ),
                if (active) ...[
                  const Divider(height: 28),
                  Row(
                    children: [
                      PullerPhoto(dataUrl: live.pullerPhoto, size: 58),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              live.pullerName.isEmpty ? 'Active puller' : live.pullerName,
                              style: const TextStyle(fontWeight: FontWeight.w800),
                            ),
                            Text('Puller ID: ${live.pullerCode.isEmpty ? '---' : live.pullerCode}'),
                            Text('Started: ${formatTimestamp(live.startedAt)}'),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  FilledButton.icon(
                    style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
                    onPressed: onEnd,
                    icon: const Icon(Icons.stop),
                    label: const Text('END SESSION'),
                  ),
                ] else ...[
                  const SizedBox(height: 14),
                  FilledButton.icon(
                    onPressed: () {
                      Navigator.of(context).push<bool>(
                        MaterialPageRoute(
                          builder: (_) => StartSessionScreen(
                            service: service,
                            owner: owner,
                            rickshaw: rickshaw,
                          ),
                        ),
                      );
                    },
                    icon: const Icon(Icons.contactless),
                    label: const Text('START SESSION'),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}

class _InlineNotice extends StatelessWidget {
  const _InlineNotice({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            Icon(icon),
            const SizedBox(width: 12),
            Expanded(child: Text(text)),
          ],
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(message, textAlign: TextAlign.center),
      ),
    );
  }
}
