# AI-PR-Reviewer
Basic function of this code is if you commment @aiprreview in youe pull request it submits PR for reviews from Azure DevOps to your AI in our case its open source llama. It is a Python script that leverages Open source AI to automatically review pr changes by senfing git diff to AI. It pushes git pr through our prompt to review change and provide structured feedback .

# High-Level Architecture

Workflow

Developer creates PR in Azure DevOps
A Service Hook / Pipeline Trigger fires
A small AI Reviewer Service runs
It:
Fetches PR diff
Sends diff to Mistral AI
Gets review suggestions

Posts comments back to the PR 
Focus on:
- bugs
- security vulnerabilities
- performance
- missing tests
- architecture issues

# Cost Optimization

Strategies:

Only review changed files

Skip large files (>1000 lines)

Skip generated files

# Table of Contents

# Features
Does not automatically take all PR's but only where you comment @aiprreview. This has been done for cost efficiency to send pr review only for those we want. 
Provides feedback on pr changes and security issues
Generates structured feedback. 
The AI willl provide feedback only on the git difff anf not the entire code keeping costing into mind. 

# Prerequisite

# Getting started

# Installation 
# Usage and FAQ

