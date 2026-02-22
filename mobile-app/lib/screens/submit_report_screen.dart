import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import 'package:record/record.dart';
import 'package:path_provider/path_provider.dart';

import '../services/report_service.dart';

/// Main report submission screen.
/// Supports text, audio recording, and image attachment.
class SubmitReportScreen extends StatefulWidget {
  const SubmitReportScreen({super.key});

  @override
  State<SubmitReportScreen> createState() => _SubmitReportScreenState();
}

class _SubmitReportScreenState extends State<SubmitReportScreen> {
  final _textController = TextEditingController();
  final _locationController = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  // Category selection
  String? _selectedCategory;
  final List<Map<String, String>> _categories = [
    {'key': 'corruption', 'label': '💰 Corruption'},
    {'key': 'crime_signals', 'label': '🚨 Crime Signal'},
    {'key': 'public_safety', 'label': '⚠️ Public Safety'},
    {'key': 'infrastructure', 'label': '🏗️ Infrastructure'},
    {'key': 'health_sanitation', 'label': '🏥 Health Risk'},
    {'key': 'environmental_risks', 'label': '🌿 Environment'},
    {'key': 'service_delivery', 'label': '📋 Service Failure'},
    {'key': 'terrorism', 'label': '🔴 Terrorism'},
  ];

  // Audio recording state
  final AudioRecorder _recorder = AudioRecorder();
  bool _isRecording = false;
  String? _audioPath;
  Timer? _recordingTimer;
  int _recordingSeconds = 0;

  // Image
  File? _selectedImage;
  final ImagePicker _imagePicker = ImagePicker();

  // Submission state
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    // Pre-select category if passed from home screen
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final category = ModalRoute.of(context)?.settings.arguments as String?;
      if (category != null) {
        setState(() => _selectedCategory = category);
      }
    });
  }

  @override
  void dispose() {
    _textController.dispose();
    _locationController.dispose();
    _recorder.dispose();
    _recordingTimer?.cancel();
    super.dispose();
  }

  // ─── Audio Recording ──────────────────────────────────────────────────────

  Future<void> _startRecording() async {
    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) {
      _showSnackBar('Microphone permission required', isError: true);
      return;
    }

    final dir = await getTemporaryDirectory();
    final path = '${dir.path}/report_audio_${DateTime.now().millisecondsSinceEpoch}.wav';

    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.wav),
      path: path,
    );

    setState(() {
      _isRecording = true;
      _recordingSeconds = 0;
    });

    _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() => _recordingSeconds++);
      if (_recordingSeconds >= 120) {
        // Max 2 minutes
        _stopRecording();
      }
    });
  }

  Future<void> _stopRecording() async {
    _recordingTimer?.cancel();
    final path = await _recorder.stop();

    setState(() {
      _isRecording = false;
      _audioPath = path;
    });

    if (path != null) {
      _showSnackBar('Audio recorded (${_recordingSeconds}s)');
    }
  }

  // ─── Image Picker ─────────────────────────────────────────────────────────

  Future<void> _pickImage() async {
    final result = await _imagePicker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 80, // Reduce file size
      maxWidth: 1920,
    );
    if (result != null) {
      setState(() => _selectedImage = File(result.path));
      _showSnackBar('Image attached');
    }
  }

  Future<void> _takePhoto() async {
    final result = await _imagePicker.pickImage(
      source: ImageSource.camera,
      imageQuality: 80,
      maxWidth: 1920,
    );
    if (result != null) {
      setState(() => _selectedImage = File(result.path));
      _showSnackBar('Photo attached');
    }
  }

  // ─── Submission ───────────────────────────────────────────────────────────

  Future<void> _submitReport() async {
    if (_textController.text.trim().isEmpty && _audioPath == null && _selectedImage == null) {
      _showSnackBar('Please add a description, audio, or image', isError: true);
      return;
    }

    setState(() => _isSubmitting = true);

    try {
      final service = context.read<ReportService>();
      final reportId = await service.submitReport(
        textContent: _textController.text.trim(),
        userCategory: _selectedCategory,
        locationHint: _locationController.text.trim(),
        audioPath: _audioPath,
        imagePath: _selectedImage?.path,
      );

      if (!mounted) return;

      Navigator.pushReplacementNamed(
        context,
        '/confirmation',
        arguments: reportId,
      );
    } catch (e) {
      if (!mounted) return;
      _showSnackBar('Submission failed: ${e.toString()}', isError: true);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  void _showSnackBar(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? Colors.red.shade700 : Colors.green.shade700,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }

  // ─── Build ────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('New Report'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            // Privacy reminder
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.blue.shade100),
              ),
              child: const Row(
                children: [
                  Icon(Icons.lock, color: Colors.blue, size: 16),
                  SizedBox(width: 8),
                  Text(
                    'This report is 100% anonymous',
                    style: TextStyle(color: Colors.blue, fontSize: 12, fontWeight: FontWeight.w500),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Category selector
            _SectionLabel(label: 'Category'),
            const SizedBox(height: 8),
            _CategoryDropdown(
              categories: _categories,
              value: _selectedCategory,
              onChanged: (val) => setState(() => _selectedCategory = val),
            ),

            const SizedBox(height: 20),

            // Text input
            _SectionLabel(label: 'Description'),
            const SizedBox(height: 8),
            TextFormField(
              controller: _textController,
              maxLines: 6,
              maxLength: 5000,
              decoration: InputDecoration(
                hintText:
                    'Describe what you witnessed. Be as specific as possible.\n\nDo NOT include your name or identifying information.',
                hintStyle: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide(color: Colors.grey.shade200),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide(color: Colors.grey.shade200),
                ),
                filled: true,
                fillColor: Colors.white,
              ),
            ),

            const SizedBox(height: 20),

            // Audio recording
            _SectionLabel(label: 'Audio Recording (Optional)'),
            const SizedBox(height: 8),
            _AudioRecordWidget(
              isRecording: _isRecording,
              hasRecording: _audioPath != null,
              recordingSeconds: _recordingSeconds,
              onStart: _startRecording,
              onStop: _stopRecording,
              onDelete: () => setState(() => _audioPath = null),
            ),

            const SizedBox(height: 20),

            // Image attachment
            _SectionLabel(label: 'Image Attachment (Optional)'),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: _AttachButton(
                    icon: Icons.photo_library,
                    label: 'Gallery',
                    onTap: _pickImage,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _AttachButton(
                    icon: Icons.camera_alt,
                    label: 'Camera',
                    onTap: _takePhoto,
                  ),
                ),
              ],
            ),
            if (_selectedImage != null) ...[
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Stack(
                  children: [
                    Image.file(_selectedImage!, height: 120, width: double.infinity, fit: BoxFit.cover),
                    Positioned(
                      top: 8,
                      right: 8,
                      child: GestureDetector(
                        onTap: () => setState(() => _selectedImage = null),
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.black54,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          padding: const EdgeInsets.all(4),
                          child: const Icon(Icons.close, color: Colors.white, size: 16),
                        ),
                      ),
                    ),
                    Container(
                      height: 28,
                      width: double.infinity,
                      color: Colors.green.shade700,
                      alignment: Alignment.center,
                      child: const Text(
                        '✓ EXIF metadata will be removed before upload',
                        style: TextStyle(color: Colors.white, fontSize: 11),
                      ),
                    ),
                  ],
                ),
              ),
            ],

            const SizedBox(height: 20),

            // Location hint (optional, not GPS)
            _SectionLabel(label: 'Area (Optional)'),
            const SizedBox(height: 8),
            TextField(
              controller: _locationController,
              decoration: InputDecoration(
                hintText: 'e.g., "Northern District", "City Hospital area"',
                hintStyle: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                prefixIcon: const Icon(Icons.location_on_outlined, color: Colors.grey),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide(color: Colors.grey.shade200),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide(color: Colors.grey.shade200),
                ),
                filled: true,
                fillColor: Colors.white,
                helperText: 'General area only — no GPS coordinates stored',
                helperStyle: const TextStyle(fontSize: 11),
              ),
            ),

            const SizedBox(height: 32),

            // Submit button
            SizedBox(
              height: 56,
              child: ElevatedButton(
                onPressed: _isSubmitting ? null : _submitReport,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF1A73E8),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                child: _isSubmitting
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                      )
                    : const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.send, size: 18),
                          SizedBox(width: 8),
                          Text('Submit Anonymously', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                        ],
                      ),
              ),
            ),

            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}

// ─── Helper Widgets ─────────────────────────────────────────────────────────

class _SectionLabel extends StatelessWidget {
  final String label;
  const _SectionLabel({required this.label});

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Color(0xFF374151)),
    );
  }
}

class _CategoryDropdown extends StatelessWidget {
  final List<Map<String, String>> categories;
  final String? value;
  final ValueChanged<String?> onChanged;

  const _CategoryDropdown({
    required this.categories,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: DropdownButton<String>(
        value: value,
        isExpanded: true,
        underline: const SizedBox(),
        hint: const Text('Select category'),
        items: categories.map((cat) {
          return DropdownMenuItem<String>(
            value: cat['key'],
            child: Text(cat['label']!),
          );
        }).toList(),
        onChanged: onChanged,
      ),
    );
  }
}

class _AudioRecordWidget extends StatelessWidget {
  final bool isRecording;
  final bool hasRecording;
  final int recordingSeconds;
  final VoidCallback onStart;
  final VoidCallback onStop;
  final VoidCallback onDelete;

  const _AudioRecordWidget({
    required this.isRecording,
    required this.hasRecording,
    required this.recordingSeconds,
    required this.onStart,
    required this.onStop,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isRecording ? Colors.red.shade300 : Colors.grey.shade200,
        ),
      ),
      child: Row(
        children: [
          GestureDetector(
            onTap: isRecording ? onStop : onStart,
            child: Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: isRecording ? Colors.red : const Color(0xFF1A73E8),
                shape: BoxShape.circle,
              ),
              child: Icon(
                isRecording ? Icons.stop : Icons.mic,
                color: Colors.white,
                size: 22,
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isRecording
                      ? '🔴 Recording... ${recordingSeconds}s / 120s'
                      : hasRecording
                          ? '✅ Audio recorded'
                          : 'Tap to record audio message',
                  style: TextStyle(
                    color: isRecording ? Colors.red : Colors.grey.shade700,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                if (!isRecording && !hasRecording)
                  Text(
                    'Audio metadata is removed before sending',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 11),
                  ),
              ],
            ),
          ),
          if (hasRecording && !isRecording)
            IconButton(
              icon: const Icon(Icons.delete_outline, color: Colors.red),
              onPressed: onDelete,
            ),
        ],
      ),
    );
  }
}

class _AttachButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _AttachButton({required this.icon, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 52,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.grey.shade200),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 18, color: Colors.grey.shade600),
            const SizedBox(width: 8),
            Text(label, style: TextStyle(color: Colors.grey.shade700, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}
