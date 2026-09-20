String formatTimestamp(String raw) {
  if (raw.trim().isEmpty) return '---';
  try {
    final date = DateTime.parse(raw).toLocal();
    String two(int v) => v.toString().padLeft(2, '0');
    return '${date.year}-${two(date.month)}-${two(date.day)} '
        '${two(date.hour)}:${two(date.minute)}:${two(date.second)}';
  } catch (_) {
    return raw;
  }
}
