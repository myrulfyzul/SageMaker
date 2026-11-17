import 'package:flutter/material.dart';

/// The SAGEMAKER ASIA wordmark from www.sagemaker.asia (its own lettering, so
/// the brand name always looks like the website). Shown in the original sage
/// green, or tinted with [color] (e.g. white on the dark green panels).
class SageMakerLogo extends StatelessWidget {
  const SageMakerLogo({super.key, this.height = 36, this.color});

  static const asset = 'assets/brand/sagemaker_logo.png';

  /// Original colour of the wordmark.
  static const sage = Color(0xFF869B74);

  final double height;
  final Color? color;

  @override
  Widget build(BuildContext context) => Semantics(
        label: 'SageMaker Asia',
        image: true,
        child: ExcludeSemantics(
          child: Image.asset(
            asset,
            height: height,
            fit: BoxFit.contain,
            filterQuality: FilterQuality.high,
            color: color,
            colorBlendMode: color == null ? null : BlendMode.srcIn,
            // Keeps the layout if the asset is ever missing.
            errorBuilder: (_, __, ___) => SizedBox(
              height: height,
              child: FittedBox(
                child: Text('SAGEMAKER',
                    style: TextStyle(
                        color: color ?? sage,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 2)),
              ),
            ),
          ),
        ),
      );
}
