// @ts-nocheck
import { openai } from "@ai-sdk/openai";
import { streamText } from "ai";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const { messages, context } = await req.json();

    // The context can be a stringified version of the CRM data 
    // passed from the frontend (so we don't have to fetch it here if not needed, 
    // or we could fetch it securely here).
    
    // If no OpenAI API Key, fallback to a mocked stream
    if (!process.env.OPENAI_API_KEY) {
      const mockEncoder = new TextEncoder();
      const mockStream = new ReadableStream({
        async start(controller) {
          const text = "Hi! I am the AI Assistant. It looks like you haven't configured an `OPENAI_API_KEY` in your environment variables yet. \n\nOnce you add a key, I can analyze your CRM pipeline and answer questions about your leads and opportunities!";
          const words = text.split(" ");
          
          for (let i = 0; i < words.length; i++) {
            // We simulate the stream format of Vercel AI SDK
            // The format is `0:"word "` for text parts
            controller.enqueue(mockEncoder.encode(`0:"${words[i]} "\n`));
            await new Promise((r) => setTimeout(r, 50));
          }
          controller.close();
        },
      });
      return new Response(mockStream, {
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "X-Vercel-AI-Data-Stream": "v1",
        },
      });
    }

    const systemPrompt = `You are a helpful and expert CRM Assistant. 
You answer questions about the user's CRM data clearly and concisely.

Here is the current CRM context available to you:
${context ? JSON.stringify(context, null, 2) : "No CRM context provided."}
`;

    const result = await streamText({
      model: openai("gpt-4o-mini"),
      messages: [
        { role: "system", content: systemPrompt },
        ...messages
      ],
      temperature: 0.2,
    });

    return result.toDataStreamResponse();
  } catch (error) {
    console.error("AI Chat Error:", error);
    return NextResponse.json({ error: "Failed to process AI request" }, { status: 500 });
  }
}
