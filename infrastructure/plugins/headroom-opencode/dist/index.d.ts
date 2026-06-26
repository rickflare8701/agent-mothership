import { CompressResult } from 'headroom-ai';
import { Plugin } from '@opencode-ai/plugin';

interface HeadroomModelMapping {
    name: string;
    limit: {
        context: number;
        output: number;
    };
}
interface HeadroomProviderOptions {
    proxyBaseUrl?: string;
    proxyPort?: number;
    defaultModel?: string;
    models?: Record<string, HeadroomModelMapping>;
}
declare const DEFAULT_MODELS: Record<string, HeadroomModelMapping>;
declare const DEFAULT_MODEL = "claude-sonnet-4-6";
interface HeadroomProvider {
    npm: string;
    name: string;
    options: {
        baseURL: string;
        apiKey?: string;
    };
    models: Record<string, HeadroomModelMapping>;
}
declare function createHeadroomProvider(options?: HeadroomProviderOptions): HeadroomProvider;
declare function buildOpencodeConfigContent(options?: HeadroomProviderOptions): Record<string, unknown>;
declare function buildOpencodeConfigContentJson(options?: HeadroomProviderOptions): string;

declare function setDefaultProxyUrl(url: string): void;
declare function getDefaultProxyUrl(): string;
interface RetrieveToolConfig {
    proxyBaseUrl: string;
}
declare function createHeadroomRetrieveTool(config: RetrieveToolConfig): {
    name: string;
    description: string;
    parameters: {
        type: "object";
        properties: {
            hash: {
                type: string;
                description: string;
            };
            query: {
                type: string;
                description: string;
            };
        };
        required: string[];
    };
    execute: (args: {
        hash: string;
        query?: string;
    }) => Promise<string>;
};
declare function compressWithHeadroom(messages: unknown[], options?: {
    model?: string;
    tokenBudget?: number;
    proxyUrl?: string;
}): Promise<CompressResult>;

interface HeadroomOpenCodePluginOptions {
    proxyUrl?: string;
    project?: string;
    backend?: string;
    debug?: boolean;
}
declare const HeadroomPlugin: Plugin;

interface InstallOptions {
    proxyUrl: string;
    debug?: boolean;
}
declare function installHeadroomTransport(options: InstallOptions): () => void;

export { DEFAULT_MODEL, DEFAULT_MODELS, type HeadroomModelMapping, type HeadroomOpenCodePluginOptions, HeadroomPlugin, type HeadroomProvider, type HeadroomProviderOptions, type RetrieveToolConfig, buildOpencodeConfigContent, buildOpencodeConfigContentJson, compressWithHeadroom, createHeadroomProvider, createHeadroomRetrieveTool, HeadroomPlugin as default, getDefaultProxyUrl, installHeadroomTransport, setDefaultProxyUrl };
