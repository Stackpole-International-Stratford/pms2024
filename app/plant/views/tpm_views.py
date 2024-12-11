from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from ..models.tpm_models import Questions
from django.views.decorators.csrf import csrf_exempt

# List all questions
def list_questions(request):
    print("Debug: Entered list_questions view")
    questions = Questions.objects.all()
    print(f"Debug: Retrieved {questions.count()} questions")
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':  # Handle AJAX request
        questions_data = [
            {'id': q.id, 'question': q.question, 'question_group': q.question_group}
            for q in questions
        ]
        print("Debug: Returning AJAX response with questions data")
        return JsonResponse({'questions': questions_data})
    print("Debug: Rendering questions.html with context")
    return render(request, 'questions.html', {'questions': questions})


@csrf_exempt
def create_question(request):
    if request.method == 'POST':
        question_text = request.POST.get('question')
        question_group = request.POST.get('question_group')
        
        # Validate that the question_group is in the allowed choices
        valid_groups = [choice[0] for choice in Questions._meta.get_field('question_group').choices]
        if question_group not in valid_groups:
            return JsonResponse({'error': 'Invalid question group'}, status=400)

        # Create the question in the database
        question = Questions.objects.create(question=question_text, question_group=question_group)
        
        # Return the created question as JSON
        return JsonResponse({
            'id': question.id,
            'question': question.question,
            'question_group': question.question_group
        })
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def delete_question(request):
    if request.method == 'POST':
        question_id = request.POST.get('id')
        try:
            question = Questions.objects.get(id=question_id)
            question.delete()
            return JsonResponse({'message': 'Question deleted successfully'})
        except Questions.DoesNotExist:
            return JsonResponse({'error': 'Question not found'}, status=404)
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def edit_question(request):
    if request.method == 'POST':
        question_id = request.POST.get('id')
        question_text = request.POST.get('question')
        question_group = request.POST.get('question_group')

        try:
            question = Questions.objects.get(id=question_id)
            question.question = question_text
            question.question_group = question_group
            question.save()

            return JsonResponse({
                'id': question.id,
                'question': question.question,
                'question_group': question.question_group
            })
        except Questions.DoesNotExist:
            return JsonResponse({'error': 'Question not found'}, status=404)
    return JsonResponse({'error': 'Invalid request'}, status=400)