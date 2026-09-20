import 'dart:async';
import 'dart:math';


import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_database/firebase_database.dart';

import '../models/models.dart';
import 'rfid_utils.dart';
import 'google_sheet_service.dart';

class RtdbService {
  RtdbService({FirebaseDatabase? database, FirebaseAuth? auth})
      : _db = database ?? FirebaseDatabase.instance,
        _auth = auth ?? FirebaseAuth.instance;

  final FirebaseDatabase _db;
  final FirebaseAuth _auth;
  final GoogleSheetService _googleSheet =
      googleSheetService;
  final Random _random = Random.secure();

  DatabaseReference get _root => _db.ref();

  Stream<bool> get connectionStream => _db.ref('.info/connected').onValue.map(
        (event) => event.snapshot.value == true,
      );

  Future<OwnerAccess> loadAccess() async {
    final user = _auth.currentUser;
    if (user == null) throw StateError('Not signed in.');

    final snapshot = await _db.ref('mobile_access/${user.uid}').get();
    if (!snapshot.exists) {
      throw StateError(
        'This login is not linked to a rickshaw owner. Ask the administrator to create mobile access.',
      );
    }

    final access = OwnerAccess.fromMap(user.uid, stringMap(snapshot.value));
    if (!access.active) {
      throw StateError('This mobile account has been disabled.');
    }
    return access;
  }

  Future<OwnerProfile> loadOwner(int ownerId) async {
    final snapshot = await _db.ref('mobile/owners/$ownerId').get();
    if (!snapshot.exists) throw StateError('Owner record not found.');
    return OwnerProfile.fromMap(stringMap(snapshot.value));
  }

  Stream<List<Rickshaw>> watchRickshaws(int ownerId) {
    final query = _db
        .ref('master/rickshaws')
        .orderByChild('owner_id')
        .equalTo(ownerId);

    return query.onValue.map((event) {
      final root = stringMap(event.snapshot.value);
      final items = <Rickshaw>[];
      for (final value in root.values) {
        final map = stringMap(value);
        if (map.isEmpty) continue;
        final item = Rickshaw.fromMap(map);
        if (item.active && item.ownerId == ownerId) items.add(item);
      }
      items.sort((a, b) => a.number.compareTo(b.number));
      return items;
    });
  }

  Stream<List<ActiveSession>> watchOwnerActiveSessions(int ownerId) {
    final query = _db
        .ref('live/active_sessions')
        .orderByChild('owner_id')
        .equalTo(ownerId);

    return query.onValue.map((event) {
      final root = stringMap(event.snapshot.value);
      final sessions = <ActiveSession>[];
      for (final value in root.values) {
        final map = stringMap(value);
        if (map.isEmpty) continue;
        if (textValue(map['status']).toUpperCase() != 'ACTIVE') continue;
        sessions.add(ActiveSession.fromMap(map));
      }
      sessions.sort((a, b) => b.startedAt.compareTo(a.startedAt));
      return sessions;
    });
  }

  Stream<LiveRickshaw> watchLiveRickshaw(int rickshawId) {
    return _db.ref('live/rickshaws/$rickshawId').onValue.map((event) {
      if (!event.snapshot.exists) return LiveRickshaw.idle();
      return LiveRickshaw.fromMap(stringMap(event.snapshot.value));
    });
  }

  Future<ActiveSession?> getActiveSession(int rickshawId) async {
    final snapshot = await _db.ref('live/active_sessions/$rickshawId').get();
    if (!snapshot.exists) return null;
    final map = stringMap(snapshot.value);
    if (textValue(map['status']).toUpperCase() != 'ACTIVE') return null;
    return ActiveSession.fromMap(map);
  }

  Future<bool> verifyMasterUid({
    required String uid,
    required int ownerId,
  }) async {
    final normalized = normalizeUid(uid);
    if (normalized.isEmpty) return false;

    try {
      final key = firebaseRfidKey(normalized);
      final snapshot = await _db.ref('indexes/master_cards/$key').get();
      if (!snapshot.exists) return false;
      final map = stringMap(snapshot.value);
      return normalizeUid(textValue(map['uid'])) == normalized &&
          intValue(map['owner_id']) == ownerId;
    } on FirebaseException {
      return false;
    }
  }

  Future<Puller?> getPullerBySlaveUid(String uid) async {
    final normalized = normalizeUid(uid);
    if (normalized.isEmpty) return null;

    try {
      final key = firebaseRfidKey(normalized);
      final indexSnapshot = await _db.ref('indexes/slave_cards/$key').get();
      if (!indexSnapshot.exists) return null;

      final index = stringMap(indexSnapshot.value);
      if (normalizeUid(textValue(index['uid'])) != normalized) return null;

      final pullerId = intValue(index['puller_id']);
      if (pullerId == null) return null;

      final pullerSnapshot = await _db.ref('mobile/pullers/$pullerId').get();
      if (!pullerSnapshot.exists) return null;

      final puller = Puller.fromMap(stringMap(pullerSnapshot.value));
      return puller.active ? puller : null;
    } on FirebaseException {
      return null;
    }
  }

  String _newCloudId() {
    final millis = DateTime.now().millisecondsSinceEpoch;
    final randomPart = List.generate(
      10,
      (_) => _random.nextInt(36).toRadixString(36),
    ).join();
    return 'sess_mobile_${millis}_$randomPart';
  }

  String _now() => DateTime.now().toUtc().toIso8601String();

  Map<String, Object?> _activePayload({
    required String cloudId,
    required Rickshaw rickshaw,
    required OwnerProfile owner,
    required Puller puller,
    required String masterUid,
    required String slaveUid,
    required String startedAt,
  }) {
    return <String, Object?>{
      'cloud_session_id': cloudId,
      'local_session_id': null,
      'rickshaw_id': rickshaw.id,
      'rickshaw_id_key': rickshaw.id.toString(),
      'rickshaw_number': rickshaw.number,
      'registration_number': rickshaw.registrationNumber,
      'qr_token': rickshaw.qrToken,
      'owner_id': owner.id,
      'owner_id_key': owner.id.toString(),
      'owner_name': owner.name,
      'owner_code': owner.ownerCode,
      'puller_id': puller.id,
      'puller_id_key': puller.id.toString(),
      'puller_name': puller.name,
      'puller_code': puller.pullerCode,
      'puller_phone': puller.phone,
      'puller_photo': '',
      'master_uid': normalizeUid(masterUid),
      'slave_uid': normalizeUid(slaveUid),
      'started_at': startedAt,
      'ended_at': null,
      'status': 'ACTIVE',
      'source': 'MOBILE',
      'mobile_uid': _auth.currentUser?.uid ?? '',
      'updated_at': _now(),
    };
  }

  Map<String, Object?> _activeProjectionUpdates({
    required Rickshaw rickshaw,
    required Puller puller,
    required Map<String, Object?> session,
  }) {
    final rid = rickshaw.id.toString();
    final token = rickshaw.qrToken;
    final cloudId = session['cloud_session_id'];
    final startedAt = session['started_at'];
    final now = _now();

    final updates = <String, Object?>{
      'history/sessions/$cloudId': <String, Object?>{
        ...session,
        'history_status': 'ACTIVE',
      },
      'live/rickshaws/$rid/status': 'ACTIVE',
      'live/rickshaws/$rid/cloud_session_id': cloudId,
      'live/rickshaws/$rid/puller_id': puller.id,
      'live/rickshaws/$rid/puller_name': puller.name,
      'live/rickshaws/$rid/puller_code': puller.pullerCode,
      'live/rickshaws/$rid/puller_phone': puller.phone,
      'live/rickshaws/$rid/started_at': startedAt,
      'live/rickshaws/$rid/ended_at': null,
      'live/rickshaws/$rid/updated_at': now,
    };

    if (token.isNotEmpty) {
      updates.addAll(<String, Object?>{
        'public/by_token/$token/status': 'ACTIVE',
        'public/by_token/$token/cloud_session_id': cloudId,
        'public/by_token/$token/puller_id': puller.id,
        'public/by_token/$token/puller_name': puller.name,
        'public/by_token/$token/puller_code': puller.pullerCode,
        'public/by_token/$token/puller_phone': puller.phone,
        'public/by_token/$token/started_at': startedAt,
        'public/by_token/$token/ended_at': null,
        'public/by_token/$token/updated_at': now,
      });
    }

    return updates;
  }

  Future<void> _retryUpdate(
    Map<String, Object?> updates, {
    int attempts = 3,
  }) async {
    Object? lastError;
    for (var attempt = 1; attempt <= attempts; attempt++) {
      try {
        await _root.update(updates);
        return;
      } catch (error) {
        lastError = error;
        if (attempt < attempts) {
          await Future<void>.delayed(Duration(milliseconds: 600 * attempt));
        }
      }
    }
    throw StateError('Firebase projection update failed: $lastError');
  }

  Future<StartSessionResult> startSession({
    required Rickshaw rickshaw,
    required OwnerProfile owner,
    required Puller puller,
    required String masterUid,
    required String slaveUid,
  }) async {
    final user = _auth.currentUser;
    if (user == null) {
      return const StartSessionResult(
        started: false,
        message: 'Please sign in again.',
      );
    }

    if (rickshaw.ownerId != owner.id) {
      return const StartSessionResult(
        started: false,
        message: 'This rickshaw is not assigned to your owner account.',
      );
    }

    final cloudId = _newCloudId();
    final startedAt = _now();
    final payload = _activePayload(
      cloudId: cloudId,
      rickshaw: rickshaw,
      owner: owner,
      puller: puller,
      masterUid: masterUid,
      slaveUid: slaveUid,
      startedAt: startedAt,
    );

    final activeRef = _db.ref('live/active_sessions/${rickshaw.id}');
    var conflict = false;

    try {
      final transaction = await activeRef.runTransaction(
        (Object? current) {
          if (current is Map && current.isNotEmpty) {
            final currentMap = stringMap(current);
            if (textValue(currentMap['status']).toUpperCase() == 'ACTIVE') {
              conflict = true;
              return Transaction.abort();
            }
          }
          return Transaction.success(payload);
        },
        applyLocally: false,
      );

      if (!transaction.committed) {
        return StartSessionResult(
          started: false,
          message: conflict
              ? 'This rickshaw already has an active session.'
              : 'The session could not be started.',
        );
      }

      await _retryUpdate(
        _activeProjectionUpdates(
          rickshaw: rickshaw,
          puller: puller,
          session: payload,
        ),
      );
      await _googleSheet.sendSession(
        Map<String, dynamic>.from(
          payload,
        ),
      );

      if (puller.photo.startsWith('data:image/')) {
        try {
          final photoUpdates = <String, Object?>{
            'live/rickshaws/${rickshaw.id}/puller_photo': puller.photo,
          };
          if (rickshaw.qrToken.isNotEmpty) {
            photoUpdates['public/by_token/${rickshaw.qrToken}/puller_photo'] =
                puller.photo;
          }
          await _root.update(photoUpdates);
        } catch (_) {
          // Photo is optional. ACTIVE state has already been committed.
        }
      }

      return StartSessionResult(
        started: true,
        message: 'Session activated successfully.',
        cloudSessionId: cloudId,
      );
    } on FirebaseException catch (error) {
      return StartSessionResult(
        started: false,
        message: error.code == 'permission-denied'
            ? 'Permission denied. Check the mobile database rules and owner account mapping.'
            : 'Firebase error: ${error.message ?? error.code}',
      );
    } catch (error) {
      return StartSessionResult(
        started: false,
        message: 'Unable to start session: $error',
      );
    }
  }

  Future<String> endSession({
    required Rickshaw rickshaw,
    required OwnerProfile owner,
  }) async {
    final ref = _db.ref('live/active_sessions/${rickshaw.id}');
    final snapshot = await ref.get();
    final endedAt = _now();

    final updates = <String, Object?>{};
    Map<String, dynamic>? current;

    if (snapshot.exists) {
      current = stringMap(snapshot.value);
      if (intValue(current['owner_id']) != owner.id) {
        throw StateError('A different owner session is active on this rickshaw.');
      }

      final cloudId = textValue(current['cloud_session_id']);
      if (cloudId.isNotEmpty) {
        updates['history/sessions/$cloudId'] = <String, Object?>{
          ...current,
          'ended_at': endedAt,
          'status': 'COMPLETED',
          'history_status': 'COMPLETED',
          'ended_by': 'MOBILE',
          'reason': '',
          'updated_at': endedAt,
        };
      }
      updates['live/active_sessions/${rickshaw.id}'] = null;
    }

    updates.addAll(<String, Object?>{
      'live/rickshaws/${rickshaw.id}/status': 'IDLE',
      'live/rickshaws/${rickshaw.id}/cloud_session_id': null,
      'live/rickshaws/${rickshaw.id}/puller_id': null,
      'live/rickshaws/${rickshaw.id}/puller_name': '',
      'live/rickshaws/${rickshaw.id}/puller_code': '',
      'live/rickshaws/${rickshaw.id}/puller_photo': '',
      'live/rickshaws/${rickshaw.id}/started_at': null,
      'live/rickshaws/${rickshaw.id}/ended_at': endedAt,
      'live/rickshaws/${rickshaw.id}/updated_at': endedAt,
    });

    if (rickshaw.qrToken.isNotEmpty) {
      final token = rickshaw.qrToken;
      updates.addAll(<String, Object?>{
        'public/by_token/$token/status': 'IDLE',
        'public/by_token/$token/cloud_session_id': null,
        'public/by_token/$token/puller_id': null,
        'public/by_token/$token/puller_name': '',
        'public/by_token/$token/puller_code': '',
        'public/by_token/$token/puller_phone': '',
        'public/by_token/$token/puller_photo': '',
        'public/by_token/$token/started_at': null,
        'public/by_token/$token/ended_at': endedAt,
        'public/by_token/$token/updated_at': endedAt,
      });
    }

    await _root.update(updates);


    // Google Sheet update

    if(current != null){

      await _googleSheet.sendSession(

        {

          ...current,


          "status":
          "COMPLETED",


          "ended_at":
          endedAt,


          "source":
          "MOBILE",


          "updated_at":
          endedAt,

        },

      );

    }



    return current == null
        ? 'Rickshaw was already idle. Live/public state was repaired.'
        : 'Session ended successfully.';
  }
}
