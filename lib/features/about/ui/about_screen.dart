import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme.dart';
import '../../../core/widgets/ui_kit.dart';

/// About SageMaker: mission, what the app offers, and project credits.
class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  static const _pillars = [
    (
      Icons.diversity_3_outlined,
      'Women artisans',
      'Every piece is made by creative women in our artisan network, helping them earn and grow their craft.'
    ),
    (
      Icons.auto_stories_outlined,
      'Heritage & stories',
      'Batik prints and local motifs turn everyday items into stories you carry.'
    ),
    (
      Icons.handshake_outlined,
      'Made to order',
      'Need something special? Request custom totes, fabric books and corporate gifts in the app.'
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('About')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
        children: [
          const FadeSlideIn(
            child: GradientPanel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('OUR MISSION',
                      style: TextStyle(
                          color: kAccent,
                          fontSize: 11,
                          letterSpacing: 1.4,
                          fontWeight: FontWeight.w800)),
                  SizedBox(height: 8),
                  Text('Elevating Creative Women, One Community at a Time',
                      style: TextStyle(
                          fontFamily: kDisplayFont,
                          color: Colors.white,
                          fontSize: 24,
                          height: 1.2,
                          fontWeight: FontWeight.w700)),
                  SizedBox(height: 10),
                  Text(
                      'SageMaker highlights handcrafted products by women artisans, weaving heritage and storytelling into everyday items.',
                      style: TextStyle(color: Colors.white70, height: 1.45)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),
          for (final (i, p) in _pillars.indexed)
            FadeSlideIn(
              index: i + 1,
              child: Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: SoftCard(
                  child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          width: 46,
                          height: 46,
                          decoration: BoxDecoration(
                            color: const Color(0xFFE8F0EB),
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: Icon(p.$1, color: kPrimary),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(p.$2, style: theme.textTheme.titleMedium),
                                const SizedBox(height: 4),
                                Text(p.$3, style: theme.textTheme.bodyMedium),
                              ]),
                        ),
                      ]),
                ),
              ),
            ),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: () => context.go('/shop'),
            icon: const Icon(Icons.storefront_outlined),
            label: const Text('Shop the collection'),
          ),
        ],
      ),
    );
  }
}
