import 'dart:convert';

String normalizeUid(String value) => value.trim().toUpperCase();

String firebaseRfidKey(String uid) {
  final normalized = normalizeUid(uid);
  if (normalized.isEmpty) return 'EMPTY';
  return base64Url.encode(utf8.encode(normalized)).replaceAll('=', '');
}
