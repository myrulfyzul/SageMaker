import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/storage/preferences_provider.dart';

const fictionalDataNoticeText =
    'This is a demo. Use fictional names, emails and addresses. '
    'Do not enter real personal data.';

const _ackKey = 'sagemaker_fictional_notice_ack';

/// Notice that only fictional data should be entered (Req 33.6).
class FictionalDataNotice extends StatelessWidget {
  const FictionalDataNotice({super.key, this.onDismiss});

  final VoidCallback? onDismiss;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      container: true,
      label: 'Fictional data notice',
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: scheme.secondaryContainer,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Icon(Icons.info_outline, color: scheme.onSecondaryContainer),
            const SizedBox(width: 8),
            Expanded(
              child: Text(fictionalDataNoticeText,
                  style: TextStyle(color: scheme.onSecondaryContainer)),
            ),
            if (onDismiss != null)
              TextButton(onPressed: onDismiss, child: const Text('OK')),
          ],
        ),
      ),
    );
  }
}

/// Shows [FictionalDataNotice] above the app until it is acknowledged on this
/// device (first launch, Req 33.6).
class FirstLaunchNoticeGate extends ConsumerStatefulWidget {
  const FirstLaunchNoticeGate({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<FirstLaunchNoticeGate> createState() => _GateState();
}

class _GateState extends ConsumerState<FirstLaunchNoticeGate> {
  bool _dismissed = false;

  Future<void> _dismiss() async {
    setState(() => _dismissed = true);
    final prefs = await ref.read(sharedPreferencesProvider.future);
    try {
      await prefs?.setBool(_ackKey, true);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final prefs = ref.watch(sharedPreferencesProvider);
    final loaded = prefs.hasValue;
    final acknowledged = prefs.value?.getBool(_ackKey) ?? false;
    final show = loaded && !acknowledged && !_dismissed;
    if (!show) return widget.child;
    return Column(
      children: [
        Material(
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: FictionalDataNotice(onDismiss: _dismiss),
            ),
          ),
        ),
        Expanded(
          child: MediaQuery.removePadding(
              context: context, removeTop: true, child: widget.child),
        ),
      ],
    );
  }
}
