import {readFileSync} from 'fs'

export interface HookEvent {
    tool_name: string
    tool_input: {
        file_path: string
        new_string: string // treść z Edit
        content: string // treść z Write
    }
}

export function readHookEvent(): HookEvent {
    return JSON.parse(readFileSync(0, 'utf-8'))
}

export function getFilePath(event: HookEvent): string | undefined {
    return event.tool_input.file_path
}