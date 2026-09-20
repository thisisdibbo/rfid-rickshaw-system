Map<String, dynamic> stringMap(Object? value) {
  if (value is! Map) return <String, dynamic>{};
  return value.map((key, val) => MapEntry(key.toString(), val));
}

int? intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

String textValue(Object? value) => value?.toString() ?? '';

bool boolValue(Object? value) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  return value?.toString().toLowerCase() == 'true';
}

class OwnerAccess {
  const OwnerAccess({
    required this.uid,
    required this.ownerId,
    required this.ownerIdKey,
    required this.email,
    required this.active,
  });

  final String uid;
  final int ownerId;
  final String ownerIdKey;
  final String email;
  final bool active;

  factory OwnerAccess.fromMap(String uid, Map<String, dynamic> map) {
    final ownerId = intValue(map['owner_id']);
    if (ownerId == null) {
      throw const FormatException('Mobile account is missing owner_id.');
    }
    return OwnerAccess(
      uid: uid,
      ownerId: ownerId,
      ownerIdKey: textValue(map['owner_id_key']).isNotEmpty
          ? textValue(map['owner_id_key'])
          : ownerId.toString(),
      email: textValue(map['email']),
      active: map['active'] == null ? true : boolValue(map['active']),
    );
  }
}

class OwnerProfile {
  const OwnerProfile({
    required this.id,
    required this.name,
    required this.ownerCode,
    required this.phone,
    required this.garageName,
    required this.garageLocation,
  });

  final int id;
  final String name;
  final String ownerCode;
  final String phone;
  final String garageName;
  final String garageLocation;

  factory OwnerProfile.fromMap(Map<String, dynamic> map) {
    return OwnerProfile(
      id: intValue(map['db_id']) ?? 0,
      name: textValue(map['name']),
      ownerCode: textValue(map['owner_code']),
      phone: textValue(map['phone']),
      garageName: textValue(map['garage_name']),
      garageLocation: textValue(map['garage_location']),
    );
  }
}

class Rickshaw {
  const Rickshaw({
    required this.id,
    required this.number,
    required this.registrationNumber,
    required this.garageName,
    required this.garageLocation,
    required this.ownerId,
    required this.ownerName,
    required this.ownerCode,
    required this.qrToken,
    required this.active,
  });

  final int id;
  final String number;
  final String registrationNumber;
  final String garageName;
  final String garageLocation;
  final int? ownerId;
  final String ownerName;
  final String ownerCode;
  final String qrToken;
  final bool active;

  factory Rickshaw.fromMap(Map<String, dynamic> map) {
    return Rickshaw(
      id: intValue(map['db_id']) ?? 0,
      number: textValue(map['rickshaw_number']),
      registrationNumber: textValue(map['registration_number']),
      garageName: textValue(map['garage_name']),
      garageLocation: textValue(map['garage_location']),
      ownerId: intValue(map['owner_id']),
      ownerName: textValue(map['owner_name']),
      ownerCode: textValue(map['owner_code']),
      qrToken: textValue(map['qr_token']),
      active: map['active'] == null ? true : boolValue(map['active']),
    );
  }
}

class Puller {
  const Puller({
    required this.id,
    required this.name,
    required this.pullerCode,
    required this.phone,
    required this.slaveUid,
    required this.photo,
    required this.active,
  });

  final int id;
  final String name;
  final String pullerCode;
  final String phone;
  final String slaveUid;
  final String photo;
  final bool active;

  factory Puller.fromMap(Map<String, dynamic> map) {
    return Puller(
      id: intValue(map['db_id']) ?? 0,
      name: textValue(map['name']),
      pullerCode: textValue(map['puller_code']),
      phone: textValue(map['phone']),
      slaveUid: textValue(map['slave_uid']),
      photo: textValue(map['photo']),
      active: map['active'] == null ? true : boolValue(map['active']),
    );
  }
}

class LiveRickshaw {
  const LiveRickshaw({
    required this.status,
    required this.cloudSessionId,
    required this.pullerId,
    required this.pullerName,
    required this.pullerCode,
    required this.pullerPhoto,
    required this.startedAt,
    required this.endedAt,
    required this.updatedAt,
  });

  final String status;
  final String cloudSessionId;
  final int? pullerId;
  final String pullerName;
  final String pullerCode;
  final String pullerPhoto;
  final String startedAt;
  final String endedAt;
  final String updatedAt;

  bool get isActive => status.toUpperCase() == 'ACTIVE';

  factory LiveRickshaw.idle() => const LiveRickshaw(
        status: 'IDLE',
        cloudSessionId: '',
        pullerId: null,
        pullerName: '',
        pullerCode: '',
        pullerPhoto: '',
        startedAt: '',
        endedAt: '',
        updatedAt: '',
      );

  factory LiveRickshaw.fromMap(Map<String, dynamic> map) {
    return LiveRickshaw(
      status: textValue(map['status']).isEmpty ? 'IDLE' : textValue(map['status']),
      cloudSessionId: textValue(map['cloud_session_id']),
      pullerId: intValue(map['puller_id']),
      pullerName: textValue(map['puller_name']),
      pullerCode: textValue(map['puller_code']),
      pullerPhoto: textValue(map['puller_photo']),
      startedAt: textValue(map['started_at']),
      endedAt: textValue(map['ended_at']),
      updatedAt: textValue(map['updated_at']),
    );
  }
}

class ActiveSession {
  const ActiveSession({
    required this.cloudSessionId,
    required this.rickshawId,
    required this.rickshawNumber,
    required this.ownerId,
    required this.pullerId,
    required this.pullerName,
    required this.pullerCode,
    required this.masterUid,
    required this.slaveUid,
    required this.startedAt,
    required this.source,
  });

  final String cloudSessionId;
  final int rickshawId;
  final String rickshawNumber;
  final int ownerId;
  final int pullerId;
  final String pullerName;
  final String pullerCode;
  final String masterUid;
  final String slaveUid;
  final String startedAt;
  final String source;

  factory ActiveSession.fromMap(Map<String, dynamic> map) {
    return ActiveSession(
      cloudSessionId: textValue(map['cloud_session_id']),
      rickshawId: intValue(map['rickshaw_id']) ?? 0,
      rickshawNumber: textValue(map['rickshaw_number']),
      ownerId: intValue(map['owner_id']) ?? 0,
      pullerId: intValue(map['puller_id']) ?? 0,
      pullerName: textValue(map['puller_name']),
      pullerCode: textValue(map['puller_code']),
      masterUid: textValue(map['master_uid']),
      slaveUid: textValue(map['slave_uid']),
      startedAt: textValue(map['started_at']),
      source: textValue(map['source']),
    );
  }
}

class StartSessionResult {
  const StartSessionResult({
    required this.started,
    required this.message,
    this.cloudSessionId = '',
  });

  final bool started;
  final String message;
  final String cloudSessionId;
}
