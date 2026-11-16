import 'package:flutter/material.dart';

import '../../app/theme.dart';

/// Fades and slides its child up once, after [index] x 60 ms, for staggered
/// list and grid entrances.
class FadeSlideIn extends StatefulWidget {
  const FadeSlideIn({super.key, required this.child, this.index = 0});
  final Widget child;
  final int index;

  @override
  State<FadeSlideIn> createState() => _FadeSlideInState();
}

class _FadeSlideInState extends State<FadeSlideIn>
    with SingleTickerProviderStateMixin {
  static const _runMs = 520;
  late final int _delayMs = 60 * widget.index.clamp(0, 8);

  // The stagger delay is part of the animation (no timers), so nothing is
  // left pending when the widget is disposed.
  late final AnimationController _c = AnimationController(
      vsync: this, duration: Duration(milliseconds: _runMs + _delayMs))
    ..forward();
  late final Animation<double> _t = CurvedAnimation(
      parent: _c,
      curve: Interval(_delayMs / (_runMs + _delayMs), 1,
          curve: Curves.easeOutCubic));

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _t,
        child: widget.child,
        builder: (_, child) => Opacity(
          opacity: _t.value,
          child: Transform.translate(
              offset: Offset(0, 24 * (1 - _t.value)), child: child),
        ),
      );
}

/// Shrinks slightly while pressed, then calls [onTap].
class PressableScale extends StatefulWidget {
  const PressableScale({super.key, required this.child, this.onTap});
  final Widget child;
  final VoidCallback? onTap;

  @override
  State<PressableScale> createState() => _PressableScaleState();
}

class _PressableScaleState extends State<PressableScale> {
  bool _down = false;

  void _set(bool v) {
    if (widget.onTap != null && _down != v) setState(() => _down = v);
  }

  @override
  Widget build(BuildContext context) => GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: (_) => _set(true),
        onTapUp: (_) => _set(false),
        onTapCancel: () => _set(false),
        onTap: widget.onTap,
        child: AnimatedScale(
          scale: _down ? 0.96 : 1,
          duration: const Duration(milliseconds: 140),
          curve: Curves.easeOut,
          child: widget.child,
        ),
      );
}

/// Rounded panel with the emerald hero gradient and decorative circles.
class GradientPanel extends StatelessWidget {
  const GradientPanel({
    super.key,
    required this.child,
    this.gradient = kHeroGradient,
    this.padding = const EdgeInsets.all(22),
    this.radius = 28,
  });
  final Widget child;
  final Gradient gradient;
  final EdgeInsetsGeometry padding;
  final double radius;

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(radius),
        child: DecoratedBox(
          decoration: BoxDecoration(gradient: gradient),
          child: Stack(children: [
            Positioned(right: -40, top: -50, child: _circle(170, 0.10)),
            Positioned(right: 60, bottom: -70, child: _circle(140, 0.07)),
            Positioned(left: -30, bottom: -40, child: _circle(90, 0.05)),
            Padding(padding: padding, child: child),
          ]),
        ),
      );

  Widget _circle(double size, double alpha) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.white.withValues(alpha: alpha),
        ),
      );
}

/// Section title with an optional "See all" action.
class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.action, this.onAction});
  final String title;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(children: [
          Expanded(
            child:
                Text(title, style: Theme.of(context).textTheme.headlineSmall),
          ),
          if (action != null)
            TextButton(onPressed: onAction, child: Text(action!)),
        ]),
      );
}

/// Pulsing placeholder block shown while content loads.
class SkeletonBox extends StatefulWidget {
  const SkeletonBox(
      {super.key, this.width, this.height = 16, this.radius = kRadius});
  final double? width;
  final double height;
  final double radius;

  @override
  State<SkeletonBox> createState() => _SkeletonBoxState();
}

class _SkeletonBoxState extends State<SkeletonBox>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1100))
    ..repeat(reverse: true);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
        opacity: Tween(begin: 0.45, end: 1.0).animate(_c),
        child: Container(
          width: widget.width,
          height: widget.height,
          decoration: BoxDecoration(
            color: const Color(0xFFEDE6D9),
            borderRadius: BorderRadius.circular(widget.radius),
          ),
        ),
      );
}

/// Small rounded status label.
class StatusPill extends StatelessWidget {
  const StatusPill(this.text, {super.key, this.color = kPrimary, this.icon});
  final String text;
  final Color color;
  final IconData? icon;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 4),
          ],
          Text(text,
              style: TextStyle(
                  color: color, fontSize: 12, fontWeight: FontWeight.w700)),
        ]),
      );
}

/// White card with a soft shadow and large radius.
class SoftCard extends StatelessWidget {
  const SoftCard(
      {super.key,
      required this.child,
      this.padding = const EdgeInsets.all(16),
      this.onTap});
  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final card = Container(
      decoration: BoxDecoration(
        color: kCard,
        borderRadius: BorderRadius.circular(kRadiusLarge),
        boxShadow: softShadow(),
      ),
      padding: padding,
      child: child,
    );
    return onTap == null ? card : PressableScale(onTap: onTap, child: card);
  }
}
