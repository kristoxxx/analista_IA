import torch
import ollama
import os
import json
from typing import List, Tuple
import nltk
from nltk.tokenize import sent_tokenize

nltk.download('punkt', quiet=True)

class DocumentAgent:
    def __init__(self, doc_id: str, file_path: str, model: str):
        self.doc_id = doc_id
        self.file_path = file_path
        self.model = model
        self.vault_content = self.load_content()
        self.vault_embeddings = self.load_or_generate_embeddings()
        
        print(f"Número de oraciones en el documento: {len(self.vault_content)}")
        print(f"Número de incrustaciones generadas: {self.vault_embeddings.shape[0]}")

    def load_content(self) -> List[str]:
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                sentences = sent_tokenize(content)
                return sentences
        else:
            return []

    def load_or_generate_embeddings(self) -> torch.Tensor:
        embeddings_file = f"{self.doc_id}_embeddings.json"
        if os.path.exists(embeddings_file):
            print(f"Cargando incrustaciones para {self.doc_id} desde archivo...")
            try:
                with open(embeddings_file, 'r', encoding='utf-8') as infile:
                    embeddings = json.load(infile)
                    return torch.tensor(embeddings)
            except Exception as e:
                print(f"Error cargando incrustaciones desde {embeddings_file}: {e}")
                return self.generate_embeddings(embeddings_file)
        else:
            return self.generate_embeddings(embeddings_file)

    def generate_embeddings(self, embeddings_file: str) -> torch.Tensor:
        print(f"Generando incrustaciones para {self.doc_id}...")
        embeddings = []
        for sentence in self.vault_content:
            embedding = ollama.embeddings(model=self.model, prompt=sentence)
            embeddings.append(embedding['embedding'])
        
        with open(embeddings_file, 'w', encoding='utf-8') as outfile:
            json.dump(embeddings, outfile)
        
        return torch.tensor(embeddings)

    def get_relevant_context(self, query: str, top_k: int = 30, threshold: float = 0.0) -> List[Tuple[str, float]]:
        if self.vault_embeddings.nelement() == 0:
            print("No hay incrustaciones disponibles.")
            return []
        
        print(f"Dimensiones de vault_embeddings: {self.vault_embeddings.shape}")
        print(f"Número de elementos en vault_content: {len(self.vault_content)}")
        
        query_embedding = ollama.embeddings(model=self.model, prompt=query)['embedding']
        query_tensor = torch.tensor(query_embedding).unsqueeze(0)
        
        cos_scores = torch.cosine_similarity(query_tensor, self.vault_embeddings)
        top_k = min(top_k, len(cos_scores))
        top_scores, top_indices = torch.topk(cos_scores, k=top_k)
        
        relevant_context = []
        for idx, score in zip(top_indices, top_scores):
            if score.item() > threshold:
                content = self.vault_content[idx.item()].strip()
                relevant_context.append((content, score.item()))
        
        print(f"Número de fragmentos relevantes encontrados: {len(relevant_context)}")
        print(f"Puntuaciones de similitud: {[score for _, score in relevant_context]}")
        return relevant_context

    def generate_response(self, query: str, context: List[str]) -> str:
        prompt = f"""Analiza cuidadosamente la siguiente información y responde a la pregunta del usuario. 
        Sigue estas directrices estrictamente:
        1. Basa tu análisis ÚNICAMENTE en la información proporcionada. No hagas suposiciones ni inventes información.
        2. Si no hay suficiente información para responder, indícalo claramente.
        3. Responde SOLO en español.
        4. Observa y conecta todos los detalles relevantes, incluso los aparentemente insignificantes.
        5. Forma deducciones lógicas basadas SOLO en la evidencia disponible.
        6. Considera múltiples posibilidades cuando sea apropiado, pero siempre manteniendo una base en los hechos proporcionados.
        7. Diferencia claramente entre hechos confirmados y posibles deducciones.
        8. Si la información es insuficiente para una conclusión, indícalo claramente.
        9. Mantén un tono serio y profesional en todo momento.
        10. Mantén un tono profesional y objetivo.
        11. Estructura tu respuesta de la siguiente manera:
           - Hechos confirmados: (lista de hechos extraídos directamente del texto)
           - Deducciones: (lista de posibles interpretaciones basadas en los hechos)
           - Conclusiones: (resumen de las deducciones más probables, indicando claramente si hay suficiente evidencia))

        Información del documento:
        {' '.join(context)}

        Pregunta del usuario: {query}

        Respuesta:"""

        response = ollama.chat(model=self.model, messages=[
            {'role': 'system', 'content': 'Eres un asistente analítico experto. Tu tarea es analizar la información proporcionada y dar respuestas precisas y objetivas basadas únicamente en los datos disponibles. Responde siempre en español.'},
            {'role': 'user', 'content': prompt}
        ])

        return response['message']['content']
