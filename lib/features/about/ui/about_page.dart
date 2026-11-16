import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../../core/widgets/section_title.dart';

class AboutPage extends StatelessWidget {
  const AboutPage({super.key});
  @override
  Widget build(BuildContext context) => bounded(
        ListView(
          padding: const EdgeInsets.fromLTRB(18, 14, 18, 32),
          children: [
            const SectionTitle('The Sagemaker story'),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(22),
              decoration: BoxDecoration(color: forest, borderRadius: BorderRadius.circular(22)),
              child: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(Icons.diversity_3_outlined, color: gold, size: 36),
                SizedBox(height: 16),
                Text('Elevating Creative Women, One Community at a Time', style: TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w800)),
                SizedBox(height: 12),
                Text('Sagemaker highlights handcrafted products by women artisans, weaving heritage and storytelling into everyday items.', style: TextStyle(color: Color(0xFFE6F0EB), height: 1.5)),
              ]),
            ),
            const SizedBox(height: 24),
            const SectionTitle('What you will discover'),
            const SizedBox(height: 12),
            const _InfoItem(Icons.handyman_outlined, 'Handmade craft', 'Thoughtful products and gifts created by skilled artisans.'),
            const _InfoItem(Icons.menu_book_outlined, 'Culture & storytelling', 'Creative items inspired by heritage and stories.'),
            const _InfoItem(Icons.favorite_outline, 'Community impact', 'Shopping that supports women-led creative livelihoods.'),
            const SizedBox(height: 16),
            const Text('This is an independent demonstration app, not the official Sagemaker store.',
              style: TextStyle(fontSize: 12, color: Colors.black54)),
          ],
        ),
      );
}

class _InfoItem extends StatelessWidget {
  const _InfoItem(this.icon, this.title, this.body);
  final IconData icon;
  final String title;
  final String body;
  @override
  Widget build(BuildContext context) => Card(
        margin: const EdgeInsets.only(bottom: 10),
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Row(children: [
            Icon(icon, color: forest, size: 27),
            const SizedBox(width: 13),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.w700, color: deep)),
              const SizedBox(height: 4),
              Text(body, style: const TextStyle(color: Colors.black54, fontSize: 13)),
            ])),
          ]),
        ),
      );
}

