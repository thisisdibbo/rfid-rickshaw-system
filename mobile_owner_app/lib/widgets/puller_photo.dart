import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

class PullerPhoto extends StatelessWidget {
  const PullerPhoto({super.key, required this.dataUrl, this.size = 72});

  final String dataUrl;
  final double size;

  Uint8List? _decode() {
    if (!dataUrl.startsWith('data:image/')) return null;
    final comma = dataUrl.indexOf(',');
    if (comma < 0 || comma == dataUrl.length - 1) return null;
    try {
      return base64Decode(dataUrl.substring(comma + 1));
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final bytes = _decode();
    if (bytes == null) {
      return CircleAvatar(
        radius: size / 2,
        child: Icon(Icons.person, size: size * .48),
      );
    }
    return ClipOval(
      child: Image.memory(
        bytes,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => CircleAvatar(
          radius: size / 2,
          child: Icon(Icons.person, size: size * .48),
        ),
      ),
    );
  }
}
