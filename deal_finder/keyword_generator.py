"""
ChatGPT-5 based keyword generator for therapeutic area filtering.

This module generates comprehensive keyword lists using multiple temperature settings
and an LLM judge to create a final curated list.
"""

import json
import logging
from typing import List, Dict
from openai import OpenAI

logger = logging.getLogger(__name__)


class KeywordGenerator:
    """Generate TA keywords using ChatGPT-5 with multiple temperatures + LLM judge."""

    def __init__(self, api_key: str, model: str = "gpt-4"):
        """
        Initialize keyword generator.

        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-4, use gpt-5 when available)
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info(f"Initialized KeywordGenerator with model: {model}")

    def generate_keywords_for_ta(
        self,
        therapeutic_area: str,
        temperatures: List[float] = [0.2, 0.3, 0.5, 0.7, 0.8]
    ) -> Dict[str, List[str]]:
        """
        Generate keywords using multiple temperatures, then judge to final list.

        Args:
            therapeutic_area: Name of therapeutic area (e.g., "immunology_inflammation")
            temperatures: List of temperatures to try

        Returns:
            Dict with:
                - "final_keywords": Final judged keyword list
                - "all_candidates": All keywords from different temps (for transparency)
        """
        logger.info(f"Generating keywords for TA: {therapeutic_area}")
        logger.info(f"Using temperatures: {temperatures}")

        # Generate keywords at each temperature
        all_generations = []
        for temp in temperatures:
            keywords = self._generate_at_temperature(therapeutic_area, temp)
            all_generations.append({
                "temperature": temp,
                "keywords": keywords
            })
            logger.info(f"Generated {len(keywords)} keywords at temp={temp}")

        # Use LLM judge to create final list
        final_keywords = self._judge_keywords(therapeutic_area, all_generations)
        logger.info(f"Final judged list: {len(final_keywords)} keywords")

        return {
            "final_keywords": final_keywords,
            "all_candidates": all_generations
        }

    def _generate_at_temperature(self, therapeutic_area: str, temperature: float) -> List[str]:
        """
        Generate keywords at a specific temperature.

        Args:
            therapeutic_area: TA name
            temperature: Sampling temperature

        Returns:
            List of keywords
        """
        prompt = f"""You are a biotech industry expert. Generate a comprehensive list of keywords that would indicate an article is about {therapeutic_area.replace('_', ' ')}.

Consider:
1. Disease names (full names and abbreviations)
2. Mechanism of action terms (e.g., "IL-6 inhibitor", "JAK inhibitor")
3. Drug modalities (e.g., "monoclonal antibody", "small molecule")
4. Clinical terms specific to this therapeutic area
5. Relevant biomarkers and targets
6. Common treatment approaches

Requirements:
- Include both technical and lay terms
- Include abbreviations (e.g., "RA" for rheumatoid arthritis)
- Include drug targets (e.g., "TNF-alpha", "IL-17")
- Focus on terms that appear in NEWS ARTICLES about deals, not just clinical papers

Return ONLY a JSON array of keywords, nothing else.
Example format: ["keyword1", "keyword2", "keyword3"]

Generate at least 50 keywords."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a biotech industry expert. Return only valid JSON arrays."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=temperature,
                max_completion_tokens=4000  # Enough for 100+ keywords
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()

            keywords = json.loads(content)

            if not isinstance(keywords, list):
                logger.error(f"Expected list, got {type(keywords)}")
                return []

            return keywords

        except Exception as e:
            logger.error(f"Error generating keywords at temp={temperature}: {e}")
            return []

    def _judge_keywords(
        self,
        therapeutic_area: str,
        all_generations: List[Dict]
    ) -> List[str]:
        """
        Use LLM judge to select final keyword list from all generations.

        Args:
            therapeutic_area: TA name
            all_generations: List of {temperature, keywords} dicts

        Returns:
            Final curated keyword list
        """
        # Combine all keywords with counts
        keyword_counts = {}
        for gen in all_generations:
            for kw in gen["keywords"]:
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

        # Create prompt for judge
        prompt = f"""You are a biotech industry expert who is evaluating keyword lists for {therapeutic_area.replace('_', ' ')}.

Your goal is to create a comprehensive keyword list that will be used to filter biotech news articles for deals in {therapeutic_area.replace('_', ' ')}. The list should leave no false negatives in terms of deals that are relevant to {therapeutic_area.replace('_', ' ')}.

You have {len(all_generations)} keyword lists generated at different temperatures:

"""

        for gen in all_generations:
            prompt += f"\n**Temperature {gen['temperature']}**: {len(gen['keywords'])} keywords\n"
            prompt += f"{json.dumps(gen['keywords'][:20])}... (showing first 20)\n"

        prompt += f"""

Your task: Create ONE final comprehensive keyword list by:
1. Including keywords that appeared in multiple generations (high agreement)
2. Including highly specific disease/drug terms (even if only in one generation)
3. Removing overly generic terms (e.g., "therapy", "treatment" alone)
4. Removing duplicates and near-duplicates
5. Including important abbreviations

The final list should:
- Be comprehensive (include 80-150 keywords)
- Cover diseases, mechanisms, modalities, and targets
- Include both technical and lay terms
- Be suitable for matching in biotech news articles

Return ONLY a JSON array of the final keyword list, nothing else.
Example: ["keyword1", "keyword2", ...]"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert judge. Return only valid JSON arrays."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Moderate temp for judging
                max_completion_tokens=8000  # Large budget for comprehensive list
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()

            final_keywords = json.loads(content)

            if not isinstance(final_keywords, list):
                logger.error(f"Judge returned non-list: {type(final_keywords)}")
                # Fallback: use most common keywords
                sorted_kw = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)
                return [kw for kw, _ in sorted_kw[:100]]

            return final_keywords

        except Exception as e:
            logger.error(f"Error in judge: {e}")
            # Fallback: use most common keywords
            sorted_kw = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)
            return [kw for kw, _ in sorted_kw[:100]]

    def generate_stage_keywords(self, stages: List[str]) -> List[str]:
        """
        Generate stage-related keywords.

        Args:
            stages: List of stages from config (e.g., ["preclinical", "phase 1"])

        Returns:
            Expanded list of stage keywords
        """
        # Basic expansions
        stage_keywords = []

        for stage in stages:
            stage_lower = stage.lower()
            stage_keywords.append(stage_lower)

            # Add variations
            if "preclinical" in stage_lower:
                stage_keywords.extend([
                    "pre-clinical",
                    "preclinical development",
                    "discovery stage",
                    "early-stage development"
                ])
            elif "phase 1" in stage_lower or "phase i" in stage_lower:
                stage_keywords.extend([
                    "phase 1",
                    "phase I",
                    "phase i",
                    "phase-1",
                    "first-in-human",
                    "FIH"
                ])

        return list(set(stage_keywords))  # Remove duplicates

    def generate_deal_keywords(self) -> List[str]:
        """
        Generate deal-related keywords (M&A, partnerships, etc).

        Returns:
            List of deal keywords
        """
        return [
            # M&A
            "acquisition", "acquires", "acquired", "acquiring",
            "merger", "merges", "merged",
            "buyout", "takeover",

            # Partnership
            "partnership", "partners", "partnered", "partnering",
            "collaboration", "collaborates", "collaborated",
            "strategic alliance", "alliance",
            "joint venture",

            # Licensing
            "licensing", "licenses", "licensed", "license agreement",
            "license deal", "in-license", "out-license",
            "option agreement", "option to license",
            "exclusive license", "non-exclusive license",

            # General deal terms
            "deal", "agreement", "transaction",
            "signs", "signed", "inks", "inked",
            "announces", "announced"
        ]
