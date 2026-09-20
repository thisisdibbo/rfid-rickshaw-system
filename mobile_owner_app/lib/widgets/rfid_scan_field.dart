import 'dart:async';

import 'package:flutter/material.dart';

class RfidScanField extends StatefulWidget {
  const RfidScanField({
    super.key,
    required this.label,
    required this.onScan,
    this.enabled = true,
    this.autoSubmitDelay = const Duration(milliseconds: 450),
  });

  final String label;
  final ValueChanged<String> onScan;
  final bool enabled;
  final Duration autoSubmitDelay;

  @override
  State<RfidScanField> createState() => _RfidScanFieldState();
}

class _RfidScanFieldState extends State<RfidScanField> {
  final _controller = TextEditingController();
  final _focus = FocusNode();
  Timer? _timer;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _requestFocus());
  }

  @override
  void didUpdateWidget(covariant RfidScanField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.enabled && widget.enabled) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _requestFocus());
    }
  }

  void _requestFocus() {
    if (mounted && widget.enabled) _focus.requestFocus();
  }

  void _changed(String value) {
    if (!widget.enabled || _submitting) return;
    _timer?.cancel();
    if (value.trim().isEmpty) return;
    _timer = Timer(widget.autoSubmitDelay, _submit);
  }

  void _submit([String? ignored]) {
    if (!widget.enabled || _submitting) return;
    final value = _controller.text.trim();
    if (value.isEmpty) return;

    _submitting = true;
    _timer?.cancel();
    _controller.clear();
    widget.onScan(value);
    _submitting = false;
    Future<void>.delayed(const Duration(milliseconds: 100), _requestFocus);
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _controller,
      focusNode: _focus,
      enabled: widget.enabled,
      autofocus: true,
      textInputAction: TextInputAction.done,
      onChanged: _changed,
      onSubmitted: _submit,
      decoration: InputDecoration(
        labelText: widget.label,
        hintText: 'Scan card or type UID for testing',
        prefixIcon: const Icon(Icons.contactless),
        suffixIcon: IconButton(
          tooltip: 'Focus scanner field',
          onPressed: widget.enabled ? _requestFocus : null,
          icon: const Icon(Icons.center_focus_strong),
        ),
      ),
    );
  }
}
